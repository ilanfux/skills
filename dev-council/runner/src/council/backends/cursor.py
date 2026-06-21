"""Cursor SDK backend: grounded local agents that browse the repo.

This is the default and recommended backend. Each task runs as a one-shot local
Cursor agent against `cwd`, so it can Read/Grep/Glob the real code and cite
`file:line`. It is the only backend that is `grounded`.
"""

from __future__ import annotations

import os
from typing import List, Optional, Sequence

from council.backends.base import Backend, BackendTask
from council.input import AgentOutcome
from council.sdk_client import build_model_selection, run_agents_batch


class CursorBackend(Backend):
    name = "cursor"
    grounded = True

    def __init__(self, api_key_env: str = "CURSOR_API_KEY") -> None:
        self.api_key_env = api_key_env

    def _api_key(self) -> Optional[str]:
        value = os.environ.get(self.api_key_env)
        return value.strip() if value and value.strip() else None

    def check_credentials(self) -> Optional[str]:
        try:
            import cursor_sdk  # type: ignore  # noqa: F401
        except Exception as error:  # pragma: no cover - environment dependent
            return f"cursor-sdk is not installed (`pip install cursor-sdk`): {error}"
        if not self._api_key():
            return (
                f"{self.api_key_env} is not set. Get a key at "
                "https://cursor.com/dashboard/integrations and export it."
            )
        return None

    def run_batch(self, tasks: Sequence[BackendTask], cwd: str) -> List[AgentOutcome]:
        if not tasks:
            return []
        sdk_tasks = [
            (t.task_id, t.prompt, build_model_selection(t.model, t.params)) for t in tasks
        ]
        return run_agents_batch(sdk_tasks, cwd=cwd, api_key=self._api_key())
