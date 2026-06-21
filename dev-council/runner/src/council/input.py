"""Input contract and result data structures for a council run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

VALID_MODES = ("plan", "review")


@dataclass
class PersonaSpec:
    """A single advisor lens and the model it runs on."""

    key: str
    title: str
    lens: str
    model: str
    family: str
    capability: str = "medium"
    core: bool = False
    triggers: List[str] = field(default_factory=list)
    # Family-specific model parameters, e.g. {"reasoning": "high"} for GPT/Codex
    # or {"thinking": "true", "effort": "high"} for Claude. Empty = default effort.
    model_params: Dict[str, str] = field(default_factory=dict)
    # Execution backend: "cursor" (grounded local agent, default) or a provider
    # backend ("openai", "anthropic", "google"). Provider backends receive injected
    # repo context instead of browsing the repo themselves.
    backend: str = "cursor"


@dataclass
class CouncilInput:
    """Everything needed to run one council."""

    mode: str
    brief: str
    cwd: str
    stakes: str = "standard"
    roster: Optional[List[str]] = None
    peer_review_override: Optional[bool] = None
    diff_scope: Optional[str] = None

    def normalized_mode(self) -> str:
        mode = (self.mode or "").strip().lower()
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}, got {self.mode!r}")
        return mode


@dataclass
class AgentOutcome:
    """Normalized result of a single Cursor SDK agent run."""

    status: str  # "finished" | "error" | "startup_error"
    text: str
    run_id: Optional[str] = None
    agent_id: Optional[str] = None
    error_message: Optional[str] = None
    # RunResult exposes duration_ms (not token usage), so duration is our cost proxy.
    duration_ms: Optional[int] = None
    actual_model: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == "finished" and bool(self.text.strip())


@dataclass
class AdvisorResult:
    """One advisor's contribution."""

    persona: PersonaSpec
    outcome: AgentOutcome


@dataclass
class PeerReviewResult:
    """One peer review of the anonymized advisor set."""

    reviewer_for_key: str
    reviewer_model: str
    reviewer_family: str
    outcome: AgentOutcome
