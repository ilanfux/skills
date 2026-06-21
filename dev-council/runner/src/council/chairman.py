"""Chairman synthesis.

A single strong model receives the brief, the de-anonymized advisor analyses,
and the peer reviews, and produces the decisive verdict. If the Chairman run
fails, the caller falls back to a locally-assembled digest so a council run
always returns something useful.
"""

from __future__ import annotations

from typing import List, Mapping, Optional

from council.backends import BackendRegistry, BackendTask
from council.input import AdvisorResult, AgentOutcome
from council.metering import MeteringSink
from council.prompts import build_chairman_prompt


def run_chairman(
    advisors: List[AdvisorResult],
    peer_reviews: List[str],
    brief: str,
    mode: str,
    cwd: str,
    chairman_model: str,
    meter: MeteringSink,
    registry: BackendRegistry,
    chairman_backend: str = "cursor",
    chairman_params: Optional[Mapping[str, str]] = None,
) -> AgentOutcome:
    prompt = build_chairman_prompt(brief, mode, advisors, peer_reviews)
    backend = registry.get(chairman_backend)
    task = BackendTask(task_id="chairman", prompt=prompt, model=chairman_model, params=chairman_params or {})
    outcome = backend.run_batch([task], cwd=cwd)[0]
    meter.record("chairman", "chairman", chairman_model, "", outcome, backend=chairman_backend)
    return outcome
