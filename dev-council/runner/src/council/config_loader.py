"""Load and resolve persona/tier configuration.

Defaults ship inside the package (`council/defaults/`). Users override any
subset by dropping files into `~/.dev-council/`. Model ids are validated
against the account's available models, with a safe fallback so a missing slug
never crashes a run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import yaml

try:  # Python 3.10+: importlib.resources.files
    from importlib.resources import files as _resource_files
except Exception:  # pragma: no cover
    _resource_files = None  # type: ignore

from council.env import credential_env_names, hydrate_persistent_env
from council.input import PersonaSpec

USER_CONFIG_DIR = Path(os.path.expanduser("~")) / ".dev-council"


@dataclass
class Tier:
    name: str
    description: str
    convene: bool
    roster: str = "core"  # "core" | "full"
    peer_review: bool = False
    downgrade_heavy: bool = False
    downgrade_model: Optional[str] = None


@dataclass
class Config:
    default_model: str
    chairman_model: str
    peer_review_pool: Dict[str, str]
    personas: Dict[str, Dict[str, PersonaSpec]]
    tiers: Dict[str, Tier]
    chairman_params: Dict[str, str] = field(default_factory=dict)
    chairman_backend: str = "cursor"
    peer_review_backend: str = "cursor"
    # Optional per-family override of the peer-review backend, so cross-family
    # reviewers run on the right provider (e.g. {anthropic: anthropic, google: google})
    # for a no-Cursor multi-provider setup. Families not listed use peer_review_backend.
    peer_review_backends: Dict[str, str] = field(default_factory=dict)
    backends: Dict[str, dict] = field(default_factory=dict)
    budget: Dict[str, float] = field(default_factory=dict)
    model_warnings: List[str] = field(default_factory=list)

    def get_tier(self, stakes: str) -> Tier:
        key = (stakes or "standard").strip().lower()
        if key not in self.tiers:
            raise ValueError(f"unknown stakes tier {stakes!r}; known: {sorted(self.tiers)}")
        return self.tiers[key]

    def monthly_ceiling(self) -> int:
        return int(self.budget.get("monthly_agent_run_ceiling", 600))

    def warn_fraction(self) -> float:
        return float(self.budget.get("warn_fraction", 0.6))


def _read_default(filename: str) -> dict:
    if _resource_files is not None:
        text = _resource_files("council.defaults").joinpath(filename).read_text(encoding="utf-8")
    else:  # pragma: no cover
        text = (Path(__file__).parent / "defaults" / filename).read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


def _read_user_override(filename: str) -> dict:
    path = USER_CONFIG_DIR / filename
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_personas(raw_modes: dict) -> Dict[str, Dict[str, PersonaSpec]]:
    personas: Dict[str, Dict[str, PersonaSpec]] = {}
    for mode in ("plan", "review"):
        personas[mode] = {}
        for key, spec in (raw_modes.get(mode) or {}).items():
            personas[mode][key] = PersonaSpec(
                key=key,
                title=str(spec.get("title", key)),
                lens=str(spec.get("lens", "")).strip(),
                model=str(spec.get("model", "")).strip(),
                family=str(spec.get("family", "openai")).strip().lower(),
                capability=str(spec.get("capability", "medium")).strip().lower(),
                core=bool(spec.get("core", False)),
                triggers=[str(t).strip().lower() for t in (spec.get("triggers") or [])],
                model_params={str(k): str(v) for k, v in (spec.get("model_params") or {}).items()},
                backend=str(spec.get("backend", "cursor")).strip().lower() or "cursor",
            )
    return personas


def load_config() -> Config:
    personas_raw = _deep_merge(_read_default("personas.yaml"), _read_user_override("personas.yaml"))
    tiers_raw = _deep_merge(_read_default("tiers.yaml"), _read_user_override("tiers.yaml"))
    backends_raw = _deep_merge(_read_default("backends.yaml"), _read_user_override("backends.yaml"))

    tiers: Dict[str, Tier] = {}
    for name, spec in (tiers_raw.get("tiers") or {}).items():
        tiers[name] = Tier(
            name=name,
            description=str(spec.get("description", "")),
            convene=bool(spec.get("convene", True)),
            roster=str(spec.get("roster", "core")).strip().lower(),
            peer_review=bool(spec.get("peer_review", False)),
            downgrade_heavy=bool(spec.get("downgrade_heavy", False)),
            downgrade_model=(str(spec["downgrade_model"]).strip() if spec.get("downgrade_model") else None),
        )

    config = Config(
        default_model=str(personas_raw.get("default_model", "gpt-5.5")).strip(),
        chairman_model=str(personas_raw.get("chairman_model", "gpt-5.5")).strip(),
        peer_review_pool={str(k).lower(): str(v) for k, v in (personas_raw.get("peer_review_pool") or {}).items()},
        personas=_build_personas(personas_raw),
        tiers=tiers,
        chairman_params={str(k): str(v) for k, v in (personas_raw.get("chairman_params") or {}).items()},
        chairman_backend=str(personas_raw.get("chairman_backend", "cursor")).strip().lower() or "cursor",
        peer_review_backend=str(personas_raw.get("peer_review_backend", "cursor")).strip().lower() or "cursor",
        peer_review_backends={
            str(k).lower(): str(v).strip().lower()
            for k, v in (personas_raw.get("peer_review_backends") or {}).items()
        },
        backends={str(k).lower(): dict(v or {}) for k, v in (backends_raw.get("backends") or {}).items()},
        budget=dict(tiers_raw.get("budget") or {}),
    )

    # Self-heal stale editor environments (Windows): pull any missing credential
    # env vars back from the persisted registry so a key set after the editor
    # launched is still seen without a full restart.
    hydrate_persistent_env(credential_env_names(config.backends))

    return config


def resolve_models(config: Config, available: List[str]) -> Config:
    """Fall back any configured model the account cannot use to default_model.

    A model is considered usable if it appears in `available`. When `available`
    is empty (e.g. models.list() failed), no rewriting happens - we trust the
    configured slugs rather than nuking the whole roster.
    """

    if not available:
        return config

    available_set = set(available)
    warnings: List[str] = []

    def resolve(model_id: str, label: str) -> str:
        if not model_id:
            return config.default_model
        if model_id in available_set:
            return model_id
        warnings.append(f"{label}: model '{model_id}' unavailable -> falling back to '{config.default_model}'")
        return config.default_model

    # Only cursor-backed selections are validated against the Cursor catalog;
    # provider backends have their own model ids and credentials.
    if config.chairman_backend == "cursor":
        resolved_chairman = resolve(config.chairman_model, "chairman")
        if resolved_chairman != config.chairman_model:
            config.chairman_params = {}  # params are family-specific; drop on fallback
        config.chairman_model = resolved_chairman

    resolved_pool: Dict[str, str] = {}
    for family, model_id in config.peer_review_pool.items():
        backend = config.peer_review_backends.get(family, config.peer_review_backend)
        # Only validate/fallback cursor-backed pool models against the Cursor catalog.
        resolved_pool[family] = resolve(model_id, f"peer_review_pool[{family}]") if backend == "cursor" else model_id
    config.peer_review_pool = resolved_pool

    for mode, persona_map in config.personas.items():
        for key, persona in persona_map.items():
            if persona.backend != "cursor":
                continue
            resolved = resolve(persona.model, f"{mode}.{key}")
            if resolved != persona.model:
                persona.model_params = {}  # dropped: params don't transfer across families
            persona.model = resolved

    config.model_warnings = warnings
    return config


def validate_model_params(config: Config, param_catalog: Dict[str, Dict[str, Set[str]]]) -> Config:
    """Drop any model param the resolved model does not actually support.

    `param_catalog` maps model id -> {param id -> allowed values}. A param whose
    id is unknown for the model (e.g. Claude's `effort` set on a GPT model), or
    whose value is out of range, is removed and recorded as a warning rather than
    sent to the SDK where it would fail the run. Unknown models are left untouched.
    """

    if not param_catalog:
        return config  # nothing to validate against; trust the config

    warnings = list(config.model_warnings)

    def clean(model_id: str, params: Dict[str, str], label: str) -> Dict[str, str]:
        if not params:
            return params
        supported = param_catalog.get(model_id)
        if supported is None:
            return params  # model not in catalog; don't second-guess it
        cleaned: Dict[str, str] = {}
        for key, value in params.items():
            if key not in supported:
                warnings.append(
                    f"{label}: param '{key}' is not supported by '{model_id}' -> dropped"
                )
                continue
            allowed = supported[key]
            if allowed and str(value) not in allowed:
                warnings.append(
                    f"{label}: value '{value}' invalid for '{key}' on '{model_id}' "
                    f"(allowed: {', '.join(sorted(allowed))}) -> dropped"
                )
                continue
            cleaned[key] = value
        return cleaned

    if config.chairman_backend == "cursor":
        config.chairman_params = clean(config.chairman_model, config.chairman_params, "chairman")
    for mode, persona_map in config.personas.items():
        for key, persona in persona_map.items():
            if persona.backend != "cursor":
                continue  # provider param semantics differ; don't validate against Cursor's
            persona.model_params = clean(persona.model, persona.model_params, f"{mode}.{key}")

    config.model_warnings = warnings
    return config


def select_personas(
    config: Config,
    mode: str,
    tier: Tier,
    explicit_roster: Optional[List[str]],
) -> Tuple[List[PersonaSpec], List[str]]:
    """Pick the personas to convene and apply tier model downgrades.

    Returns (personas, skipped_specialist_keys).
    """

    persona_map = config.personas.get(mode, {})
    if not persona_map:
        raise ValueError(f"no personas configured for mode {mode!r}")

    if explicit_roster:
        chosen_keys = [k for k in explicit_roster if k in persona_map]
        unknown = [k for k in explicit_roster if k not in persona_map]
        if unknown:
            raise ValueError(f"unknown personas for mode {mode!r}: {unknown}")
    elif tier.roster == "full":
        chosen_keys = list(persona_map.keys())
    else:  # core only
        chosen_keys = [k for k, p in persona_map.items() if p.core]

    skipped = [k for k in persona_map if k not in chosen_keys]

    personas: List[PersonaSpec] = []
    for key in chosen_keys:
        persona = persona_map[key]
        model = persona.model
        model_params = persona.model_params
        # Downgrade only cursor-backed heavy personas: the downgrade model is a
        # Cursor id and would be meaningless on a provider backend.
        if (
            tier.downgrade_heavy
            and persona.capability == "heavy"
            and tier.downgrade_model
            and persona.backend == "cursor"
        ):
            model = tier.downgrade_model
            model_params = {}  # cheaper tier runs at default effort; params are family-specific
        personas.append(
            PersonaSpec(
                key=persona.key,
                title=persona.title,
                lens=persona.lens,
                model=model,
                family=persona.family,
                capability=persona.capability,
                core=persona.core,
                triggers=persona.triggers,
                model_params=dict(model_params),
                backend=persona.backend,
            )
        )
    return personas, skipped
