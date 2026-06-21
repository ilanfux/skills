"""OpenAI-compatible backend.

Works against the OpenAI API and any OpenAI-compatible gateway (Amdocs AutoX,
Azure-style proxies, OpenRouter, a local vLLM, ...) by pointing `base_url` at it.
Because it is a plain chat call, the persona prompt must already contain the repo
context (the dispatcher injects it for non-grounded backends).
"""

from __future__ import annotations

import time
from typing import List, Optional, Sequence

from council.backends._provider_util import env_key, finished, run_parallel, system_prompt
from council.backends.base import Backend, BackendTask
from council.input import AgentOutcome


class OpenAIBackend(Backend):
    name = "openai"
    grounded = False

    def __init__(
        self,
        api_key_env: str = "OPENAI_API_KEY",
        base_url_env: str = "OPENAI_BASE_URL",
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key_env = api_key_env
        self.base_url_env = base_url_env
        # Explicit base_url from config wins; otherwise an env override is honored.
        self.base_url = base_url or env_key(base_url_env)

    def _client(self):
        from openai import OpenAI  # lazy: optional dependency

        key = env_key(self.api_key_env)
        kwargs = {"api_key": key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    def check_credentials(self) -> Optional[str]:
        try:
            import openai  # type: ignore  # noqa: F401
        except Exception as error:
            return f"openai package not installed (`pip install 'dev-council-runner[openai]'`): {error}"
        if not env_key(self.api_key_env):
            return f"{self.api_key_env} is not set (export your OpenAI/AutoX-compatible key)."
        return None

    def run_batch(self, tasks: Sequence[BackendTask], cwd: str) -> List[AgentOutcome]:
        client = self._client()

        def _one(task: BackendTask) -> AgentOutcome:
            started = time.perf_counter()
            messages = [
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": task.prompt},
            ]
            # Pass reasoning effort when present; retry without it if rejected.
            effort = task.params.get("reasoning") if task.params else None
            try:
                if effort:
                    resp = client.chat.completions.create(
                        model=task.model, messages=messages, reasoning_effort=effort
                    )
                else:
                    resp = client.chat.completions.create(model=task.model, messages=messages)
            except Exception:
                resp = client.chat.completions.create(model=task.model, messages=messages)
            text = resp.choices[0].message.content if resp.choices else ""
            return finished(text or "", getattr(resp, "model", task.model), started)

        return run_parallel(tasks, _one)
