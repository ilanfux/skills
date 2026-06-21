"""Repo-context gathering for non-grounded (provider) backends.

Cursor-backed personas browse the repo themselves. Provider backends (OpenAI/
Anthropic/Google) are plain chat calls, so we capture a snapshot of the change
under review and prepend it to their prompt. This is lower-fidelity than an agent
that can open any file, but it keeps `file:line` citations possible.

The snapshot is bounded so we never blow up a provider context window.
"""

from __future__ import annotations

import subprocess
from typing import List, Optional

_MAX_DIFF_CHARS = 60_000
_MAX_TREE_LINES = 200


def _run_git(args: List[str], cwd: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            # Decode as UTF-8 and replace undecodable bytes: git output (diffs of
            # binary/non-latin files) is not the Windows ANSI codepage, and the
            # default cp1252 decoder would crash the reader thread.
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text) - limit} more chars] ..."


def gather_repo_context(cwd: str, diff_scope: Optional[str] = None) -> str:
    """Build a bounded text snapshot of the repo state for prompt injection.

    Prefers the uncommitted diff (working tree + staged). Falls back to the last
    commit's diff, then to a file tree, so a provider persona always has something
    concrete to ground citations in.
    """

    sections: List[str] = []
    if diff_scope:
        sections.append(f"## Change under review\n{diff_scope.strip()}")

    # Uncommitted changes (staged + unstaged), with a few lines of context.
    diff = _run_git(["diff", "HEAD", "--unified=3"], cwd)
    if not (diff and diff.strip()):
        # Nothing uncommitted; show the most recent commit instead.
        diff = _run_git(["diff", "HEAD~1", "HEAD", "--unified=3"], cwd)

    if diff and diff.strip():
        sections.append("## Diff (paths are real; cite file:line from these)\n```diff\n"
                        + _truncate(diff.strip(), _MAX_DIFF_CHARS) + "\n```")
    else:
        tree = _run_git(["ls-files"], cwd)
        if tree and tree.strip():
            lines = tree.strip().splitlines()
            shown = "\n".join(lines[:_MAX_TREE_LINES])
            if len(lines) > _MAX_TREE_LINES:
                shown += f"\n... [{len(lines) - _MAX_TREE_LINES} more files] ..."
            sections.append("## Repository files\n```\n" + shown + "\n```")

    if not sections:
        return ""
    header = (
        "You cannot browse the repository directly. The material below is your only "
        "evidence; ground every citation in it.\n\n"
    )
    return header + "\n\n".join(sections)
