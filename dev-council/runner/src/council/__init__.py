"""Standalone multi-model Dev Council runner.

Each advisor persona runs as its own agent on a different model via a pluggable
backend (Cursor SDK by default; OpenAI/AutoX, Anthropic, Google optional), reads
the real repository (or injected context), is peer-reviewed anonymously, and a
Chairman synthesizes a decisive verdict.
"""

from __future__ import annotations

__version__ = "0.2.0"

__all__ = ["__version__"]
