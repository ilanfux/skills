"""`council` command-line interface.

Subcommands:
  run       - convene the council on a brief and print the verdict markdown
  usage     - summarize metered usage and check the soft budget ceiling
  models    - list models your key can use and show persona model resolution
  backends  - show configured backends and whether their credentials are ready
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from council import __version__
from council.backends import BackendError, BackendRegistry
from council.config_loader import load_config, resolve_models, select_personas, validate_model_params
from council.input import CouncilInput
from council.env import hydrate_persistent_env
from council.metering import USAGE_LOG_PATH, summarize
from council.runner import CouncilPlan, plan_council, run_council
from council.sdk_client import SdkUnavailableError, discover_models


def main(argv: Optional[List[str]] = None) -> int:
    # Recover credential env vars an editor may have launched without (Windows);
    # safe + idempotent on every platform.
    hydrate_persistent_env()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    try:
        return args.handler(args)
    except (SdkUnavailableError, BackendError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="council", description="Multi-model Dev Council runner.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Convene the council on a brief.")
    run_p.add_argument("--mode", required=True, choices=["plan", "review"], help="PLAN (design) or REVIEW (code).")
    run_p.add_argument("--stakes", default="standard", help="Tier: trivial | standard | risky (default: standard).")
    run_p.add_argument("--cwd", default=".", help="Repository the advisors read (default: current dir).")
    run_p.add_argument("--brief", help="Brief text inline.")
    run_p.add_argument("--brief-file", help="Path to a file containing the brief.")
    run_p.add_argument("--roster", help="Comma-separated persona keys to force (overrides tier roster).")
    run_p.add_argument("--diff-scope", help="Optional description of the diff under review.")
    peer = run_p.add_mutually_exclusive_group()
    peer.add_argument("--peer-review", dest="peer_review", action="store_true", default=None, help="Force peer review on.")
    peer.add_argument("--no-peer-review", dest="peer_review", action="store_false", help="Force peer review off.")
    run_p.add_argument("--forward-db", action="store_true", help="Also forward metering rows to the FIT activity DB.")
    run_p.add_argument("--seed", type=int, help="Deterministic anonymization seed (testing).")
    run_p.add_argument("--out", help="Write verdict markdown to this file instead of stdout.")
    run_p.add_argument("--dry-run", action="store_true", help="Print the execution plan (personas, backends, models, credential readiness) without running.")
    run_p.add_argument("--json", action="store_true", help="With --dry-run, emit the plan as JSON.")
    run_p.set_defaults(handler=_cmd_run)

    usage_p = sub.add_parser("usage", help="Summarize usage and check the budget ceiling.")
    usage_p.add_argument("--month", help="Month as YYYY-MM (default: current).")
    usage_p.add_argument("--json", action="store_true", help="Emit raw JSON summary.")
    usage_p.set_defaults(handler=_cmd_usage)

    models_p = sub.add_parser("models", help="List usable models and persona resolution.")
    models_p.set_defaults(handler=_cmd_models)

    backends_p = sub.add_parser("backends", help="Show configured backends and credential status.")
    backends_p.set_defaults(handler=_cmd_backends)

    return parser


def _resolve_brief(args) -> str:
    if args.brief:
        return args.brief
    if args.brief_file:
        path = Path(args.brief_file)
        if not path.exists():
            raise FileNotFoundError(f"brief file not found: {path}")
        return path.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return data
    raise ValueError("no brief provided; use --brief, --brief-file, or pipe text on stdin.")


def _cmd_run(args) -> int:
    brief = _resolve_brief(args)
    roster = [k.strip() for k in args.roster.split(",") if k.strip()] if args.roster else None
    council_input = CouncilInput(
        mode=args.mode,
        brief=brief,
        cwd=os.path.abspath(args.cwd),
        stakes=args.stakes,
        roster=roster,
        peer_review_override=args.peer_review,
        diff_scope=args.diff_scope,
    )
    if getattr(args, "dry_run", False):
        return _emit_plan(plan_council(council_input), as_json=getattr(args, "json", False))

    _interactive_credential_check(council_input)
    result = run_council(council_input, forward_db=args.forward_db, seed=args.seed)

    if args.out:
        Path(args.out).write_text(result.markdown, encoding="utf-8")
        print(f"verdict written to {args.out}")
    else:
        print(result.markdown)
    return 0 if result.convened else 0


def _emit_plan(plan: CouncilPlan, as_json: bool = False) -> int:
    if as_json:
        payload = {
            "mode": plan.mode,
            "stakes": plan.stakes,
            "convened": plan.convened,
            "ready": plan.ready,
            "peer_review": plan.peer_review,
            "peer_review_backend": plan.peer_review_backend,
            "advisors": [vars(a) for a in plan.advisors],
            "chairman": vars(plan.chairman) if plan.chairman else None,
            "skipped": plan.skipped,
            "backend_status": {k: (v or "ready") for k, v in plan.backend_status.items()},
            "blocking_reasons": plan.blocking_reasons,
        }
        print(json.dumps(payload, indent=2))
        return 0 if plan.ready else 1

    print(f"Execution plan - mode={plan.mode.upper()}, stakes={plan.stakes}")
    if not plan.convened:
        print("  Council would NOT convene at this tier (raise --stakes to convene).")
        return 0

    print("  Backend readiness:")
    for name, reason in sorted(plan.backend_status.items()):
        print(f"    {name:10}: {'READY' if reason is None else 'NOT READY - ' + reason}")

    print("  Advisors:")
    for a in plan.advisors:
        flag = "" if plan.backend_status.get(a.backend) is None else "  <-- backend NOT READY"
        print(f"    {a.title:34} {a.backend:9} {a.model}{flag}")
    print(f"  Peer review: {'yes' if plan.peer_review else 'no'} (backend: {plan.peer_review_backend})")
    if plan.chairman:
        print(f"  Chairman: {plan.chairman.backend} {plan.chairman.model}")
    if plan.skipped:
        print(f"  Skipped personas: {', '.join(plan.skipped)}")

    if plan.ready:
        print("  Overall: READY")
        return 0
    print("  Overall: BLOCKED - resolve: " + "; ".join(plan.blocking_reasons))
    return 1


def _persist_user_env(var: str, value: str) -> bool:
    """Best-effort persist an env var for future sessions (Windows: setx)."""

    try:
        if os.name == "nt":
            subprocess.run(["setx", var, value], capture_output=True, text=True, timeout=15)
            return True
    except Exception:
        return False
    return False


def _maybe_prompt_for_key(var: str) -> None:
    """If `var` is unset and we're interactive, ask for it (hidden) for this run,
    and optionally persist it. Never echoes or logs the secret."""

    if os.environ.get(var) or not sys.stdin.isatty():
        return
    print(f"{var} is not set.", file=sys.stderr)
    try:
        value = getpass.getpass(f"Paste your {var} (hidden), or press Enter to skip: ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not value:
        return
    os.environ[var] = value
    try:
        answer = input("Save this key for future sessions? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    if answer == "y":
        if _persist_user_env(var, value):
            print(f"Saved {var} to your user environment (new terminals will see it).", file=sys.stderr)
        else:
            print(f"Could not auto-persist; set {var} in your shell profile to keep it.", file=sys.stderr)


def _interactive_credential_check(council_input: CouncilInput) -> None:
    """Before a run, prompt for any missing API key of a backend actually in use.
    Stays silent in non-interactive contexts so the run fails fast with a clear error."""

    try:
        config = load_config()
        registry = BackendRegistry(config.backends)
        mode = council_input.normalized_mode()
        tier = config.get_tier(council_input.stakes)
        if not tier.convene:
            return
        do_peer = (
            council_input.peer_review_override
            if council_input.peer_review_override is not None
            else tier.peer_review
        )
        personas, _ = select_personas(config, mode, tier, council_input.roster)
        names = {p.backend for p in personas} | {config.chairman_backend}
        if do_peer:
            names.add(config.peer_review_backend)
        for name in sorted(names):
            try:
                backend = registry.get(name)
            except BackendError:
                continue
            if backend.check_credentials():
                env_var = getattr(backend, "api_key_env", None)
                if env_var:
                    _maybe_prompt_for_key(env_var)
    except Exception:
        # A precheck must never block the real run; let run_council surface errors.
        return


def _cmd_usage(args) -> int:
    summary = summarize(month=args.month)
    config = load_config()
    ceiling = config.monthly_ceiling()
    warn_at = int(ceiling * config.warn_fraction())
    runs = int(summary["runs_this_month"])

    if args.json:
        summary["budget"] = {"monthly_ceiling": ceiling, "warn_at": warn_at}
        print(json.dumps(summary, indent=2))
        return 0

    print(f"Usage log: {USAGE_LOG_PATH}")
    print(f"Month: {summary['month']}")
    print(f"Agent runs this month: {runs} / {ceiling} (soft ceiling)")
    print(f"All-time runs: {summary['total_runs_all_time']}")
    print(f"Agent time this month: {int(summary['total_duration_ms']) / 1000:.1f}s")
    if summary["by_model"]:
        print("By model:")
        for model, count in summary["by_model"].items():
            print(f"  {model}: {count}")
    if summary["by_stage"]:
        print("By stage:", ", ".join(f"{k}={v}" for k, v in summary["by_stage"].items()))
    if summary.get("by_backend"):
        print("By backend:", ", ".join(f"{k}={v}" for k, v in summary["by_backend"].items()))
    if summary["by_status"]:
        print("By status:", ", ".join(f"{k}={v}" for k, v in summary["by_status"].items()))

    if runs >= warn_at:
        print(
            f"\nWARNING: {runs} runs this month is past the {int(config.warn_fraction() * 100)}% soft ceiling "
            f"({warn_at}/{ceiling}). Consider deferring non-risky councils or moving to the AutoX hybrid.",
            file=sys.stderr,
        )
    return 0


def _fmt_params(params) -> str:
    if not params:
        return ""
    return " [" + ", ".join(f"{k}={v}" for k, v in params.items()) + "]"


def _cmd_models(args) -> int:
    available, param_catalog = discover_models()
    print(f"Models available to your key ({len(available)}):")
    for model_id in sorted(available):
        print(f"  {model_id}")

    config = resolve_models(load_config(), available)
    validate_model_params(config, param_catalog)
    print("\nPersona model resolution:")
    for mode in ("plan", "review"):
        print(f"  [{mode}]")
        for key, persona in config.personas[mode].items():
            mark = "ok" if persona.model in set(available) else "fallback"
            params = _fmt_params(persona.model_params)
            print(f"    {key}: {persona.model} ({mark}){params}")
    print(f"  chairman: {config.chairman_model}{_fmt_params(config.chairman_params)}")
    if config.model_warnings:
        print("\nResolution warnings:")
        for warning in config.model_warnings:
            print(f"  - {warning}")
    return 0


def _cmd_backends(args) -> int:
    config = load_config()
    registry = BackendRegistry(config.backends)

    referenced = set(config.backends) | {config.chairman_backend, config.peer_review_backend}
    for mode in ("plan", "review"):
        for persona in config.personas.get(mode, {}).values():
            referenced.add(persona.backend)

    print("Backends (credentials come from environment variables only):")
    for name in sorted(referenced):
        try:
            backend = registry.get(name)
        except BackendError as error:
            print(f"  {name}: unknown - {error}")
            continue
        reason = backend.check_credentials()
        status = "ready" if not reason else f"NOT READY - {reason}"
        kind = "grounded (reads repo)" if backend.grounded else "prompt-context"
        print(f"  {name}  [{backend.name} / {kind}]: {status}")

    print("\nPersona -> backend:")
    for mode in ("plan", "review"):
        pairs = [f"{k}:{p.backend}" for k, p in config.personas.get(mode, {}).items()]
        print(f"  [{mode}] " + ", ".join(pairs))
    print(f"  chairman: {config.chairman_backend} | peer-review: {config.peer_review_backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
