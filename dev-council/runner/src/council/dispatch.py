"""Parallel advisor dispatch across pluggable backends.

Each persona runs on its configured backend and model. Cursor-backed personas
run as grounded local agents that browse the repo; provider-backed personas get
a bounded repo-context snapshot injected into their prompt. Tasks are grouped by
backend so each backend runs its set concurrently. A single failed persona is
captured as a failed AdvisorResult and never sinks the run.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from council.backends import BackendRegistry, BackendTask
from council.context import gather_repo_context
from council.input import AdvisorResult, AgentOutcome, PersonaSpec
from council.metering import MeteringSink
from council.prompts import build_advisor_prompt


def dispatch_advisors(
    personas: List[PersonaSpec],
    brief: str,
    mode: str,
    cwd: str,
    diff_scope: Optional[str],
    meter: MeteringSink,
    registry: BackendRegistry,
) -> List[AdvisorResult]:
    if not personas:
        return []

    # Compute the repo-context snapshot at most once, and only if a non-grounded
    # backend actually needs it.
    _ctx: Dict[str, str] = {}

    def repo_context() -> str:
        if "value" not in _ctx:
            _ctx["value"] = gather_repo_context(cwd, diff_scope)
        return _ctx["value"]

    tasks_by_backend: Dict[str, List[BackendTask]] = defaultdict(list)
    for persona in personas:
        grounded = registry.get(persona.backend).grounded
        prompt = build_advisor_prompt(
            persona,
            brief,
            mode,
            diff_scope,
            repo_context=None if grounded else repo_context(),
            grounded=grounded,
        )
        tasks_by_backend[persona.backend].append(
            BackendTask(task_id=persona.key, prompt=prompt, model=persona.model, params=persona.model_params)
        )

    outcomes_by_key: Dict[str, AgentOutcome] = {}
    for backend_name, tasks in tasks_by_backend.items():
        backend = registry.get(backend_name)
        for task, outcome in zip(tasks, backend.run_batch(tasks, cwd=cwd)):
            outcomes_by_key[task.task_id] = outcome

    results: List[AdvisorResult] = []
    for persona in personas:
        outcome = outcomes_by_key.get(
            persona.key,
            AgentOutcome(status="error", text="", error_message="no outcome returned"),
        )
        meter.record("advisor", persona.key, persona.model, persona.family, outcome, backend=persona.backend)
        results.append(AdvisorResult(persona=persona, outcome=outcome))
    return results
