"""Top-level council orchestration: frame -> dispatch -> peer review -> chairman."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from council.backends import BackendError, BackendRegistry
from council.chairman import run_chairman
from council.config_loader import (
    Config,
    load_config,
    resolve_models,
    select_personas,
    validate_model_params,
)
from council.dispatch import dispatch_advisors
from council.format import render_output
from council.input import CouncilInput, PersonaSpec
from council.metering import MeteringSink
from council.peer_review import run_peer_review
from council.sdk_client import ModelParamCatalog, SdkUnavailableError, discover_models


@dataclass
class CouncilRunResult:
    convened: bool
    markdown: str


def run_council(
    council_input: CouncilInput,
    forward_db: bool = False,
    api_key: Optional[str] = None,
    seed: Optional[int] = None,
    config: Optional[Config] = None,
) -> CouncilRunResult:
    mode = council_input.normalized_mode()
    config = config or load_config()
    registry = BackendRegistry(config.backends)

    tier = config.get_tier(council_input.stakes)
    if not tier.convene:
        return CouncilRunResult(
            convened=False,
            markdown=(
                f"Council not convened: stakes tier '{tier.name}' is below the threshold "
                f"({tier.description}). Re-run with a higher --stakes to convene.\n"
            ),
        )

    do_peer = council_input.peer_review_override if council_input.peer_review_override is not None else tier.peer_review

    # Only query the Cursor catalog (for fallback + param validation) when a
    # cursor-backed selection actually exists in this mode.
    if _cursor_referenced(config, mode, do_peer):
        available, param_catalog = _discover_models(api_key)
        if not available:
            raise SdkUnavailableError(
                "Could not confirm which Cursor models your key can use (the model "
                "list came back empty). Refusing to dispatch with unverified model "
                "ids/params. Check your network/CURSOR_API_KEY and run `council models`."
            )
        resolve_models(config, available)
        validate_model_params(config, param_catalog)

    personas, skipped = select_personas(config, mode, tier, council_input.roster)

    _require_backend_credentials(registry, _backends_in_use(config, personas, do_peer))

    meter = MeteringSink(mode=mode, stakes=tier.name, forward_db=forward_db)

    advisors = dispatch_advisors(
        personas=personas,
        brief=council_input.brief,
        mode=mode,
        cwd=council_input.cwd,
        diff_scope=council_input.diff_scope,
        meter=meter,
        registry=registry,
    )

    peer_reviews = []
    if do_peer:
        peer_reviews = run_peer_review(
            advisors=advisors,
            brief=council_input.brief,
            mode=mode,
            cwd=council_input.cwd,
            peer_review_pool=config.peer_review_pool,
            default_model=config.default_model,
            meter=meter,
            registry=registry,
            peer_review_backend=config.peer_review_backend,
            rng=random.Random(seed) if seed is not None else None,
        )

    peer_texts: List[str] = [p.outcome.text for p in peer_reviews if p.outcome.ok]

    chairman = run_chairman(
        advisors=advisors,
        peer_reviews=peer_texts,
        brief=council_input.brief,
        mode=mode,
        cwd=council_input.cwd,
        chairman_model=config.chairman_model,
        meter=meter,
        registry=registry,
        chairman_backend=config.chairman_backend,
        chairman_params=config.chairman_params,
    )

    markdown = render_output(
        mode=mode,
        stakes=tier.name,
        advisors=advisors,
        peer_reviews=peer_reviews,
        skipped_keys=skipped,
        chairman=chairman,
        model_warnings=config.model_warnings,
    )
    return CouncilRunResult(convened=True, markdown=markdown)


def _cursor_referenced(config: Config, mode: str, do_peer: bool) -> bool:
    if config.chairman_backend == "cursor":
        return True
    if do_peer and config.peer_review_backend == "cursor":
        return True
    return any(p.backend == "cursor" for p in config.personas.get(mode, {}).values())


def _backends_in_use(config: Config, personas: List[PersonaSpec], do_peer: bool) -> Set[str]:
    names: Set[str] = {p.backend for p in personas}
    names.add(config.chairman_backend)
    if do_peer:
        names.add(config.peer_review_backend)
    return names


def _require_backend_credentials(registry: BackendRegistry, names: Set[str]) -> None:
    """Fail fast with one clear message if any backend in use lacks credentials."""

    problems: List[str] = []
    for name in sorted(names):
        try:
            reason = registry.get(name).check_credentials()
        except BackendError as error:
            reason = str(error)
        if reason:
            problems.append(f"  - backend '{name}': {reason}")
    if problems:
        raise BackendError(
            "Cannot run: one or more configured backends are not ready.\n"
            + "\n".join(problems)
        )


def _discover_models(api_key: Optional[str]) -> Tuple[List[str], ModelParamCatalog]:
    """Best-effort (ids, param catalog). A missing key/SDK is fatal and re-raised;
    a transient models.list() failure returns empty so the caller can fail fast
    rather than dispatch with unverified model ids/params."""

    try:
        return discover_models(api_key)
    except SdkUnavailableError:
        raise
    except Exception:
        return [], {}
