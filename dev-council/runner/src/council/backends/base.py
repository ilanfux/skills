"""Backend abstraction: how a persona prompt actually gets executed.

The council was born on the Cursor SDK, where every persona is a *grounded local
agent* that reads the repo and cites `file:line`. That is the default and the
recommended backend. To support environments without a Cursor key (and to let a
single council mix families across providers), execution is pluggable:

- `cursor`  - grounded local agent via the Cursor SDK (browses the repo).
- `openai`  - OpenAI-compatible chat API (also covers AutoX and gateways via base_url).
- `anthropic` - Anthropic Messages API.
- `google`  - Google Gemini API.

Provider backends are plain chat calls: they cannot browse the repo, so the
dispatcher injects repo context (diff + cited files) into their prompts. This is
lower-fidelity grounding than the Cursor agent and is documented as such.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence

from council.input import AgentOutcome


class BackendError(RuntimeError):
    """A backend cannot run (missing dependency, missing credentials, etc.)."""


@dataclass
class BackendTask:
    """One unit of work for a backend: a prompt on a model, with optional params."""

    task_id: str
    prompt: str
    model: str
    params: Mapping[str, str] = field(default_factory=dict)


class Backend(ABC):
    """A pluggable execution engine for persona prompts."""

    #: Stable identifier used in config (`backend: <name>`).
    name: str = "base"
    #: True if the backend reads the repository itself (so no context injection).
    grounded: bool = False

    @abstractmethod
    def check_credentials(self) -> Optional[str]:
        """Return None if the backend is usable, else a human-readable reason
        (missing package, missing API key) so the caller can fail fast clearly."""

    @abstractmethod
    def run_batch(self, tasks: Sequence[BackendTask], cwd: str) -> List[AgentOutcome]:
        """Run tasks (ideally concurrently) and return outcomes in task order.

        A single failed task must be returned as a failed AgentOutcome rather than
        raising, so one persona never sinks the whole council.
        """
