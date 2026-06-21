"""Render the final council output as markdown.

Primary output is the Chairman's verdict. This module wraps it with a convened/
skipped header and, if the Chairman failed, assembles a readable fallback digest
from the raw advisor and peer-review responses.
"""

from __future__ import annotations

from typing import List

from council.input import AdvisorResult, AgentOutcome, PersonaSpec, PeerReviewResult


def _model_label(persona: PersonaSpec) -> str:
    """`model` for the default Cursor backend; `model@backend` otherwise."""

    if persona.backend and persona.backend != "cursor":
        return f"{persona.model}@{persona.backend}"
    return persona.model


def render_output(
    mode: str,
    stakes: str,
    advisors: List[AdvisorResult],
    peer_reviews: List[PeerReviewResult],
    skipped_keys: List[str],
    chairman: AgentOutcome,
    model_warnings: List[str],
) -> str:
    parts: List[str] = []
    parts.append(_header(mode, stakes, advisors, skipped_keys, peer_reviews))

    if model_warnings:
        parts.append("> Model fallbacks applied:\n" + "\n".join(f"> - {w}" for w in model_warnings))

    if chairman.ok:
        parts.append(chairman.text.strip())
    else:
        parts.append(
            f"> Chairman synthesis unavailable ({chairman.status}: {chairman.error_message}). "
            "Raw council inputs below."
        )
        parts.append(_fallback_digest(advisors, peer_reviews))

    failed = [a for a in advisors if not a.outcome.ok]
    if failed:
        parts.append(
            "### Advisors that failed to respond\n"
            + "\n".join(
                f"- {a.persona.title} ({a.persona.model}): {a.outcome.status} - {a.outcome.error_message}"
                for a in failed
            )
        )

    return "\n\n".join(p for p in parts if p.strip()) + "\n"


def _header(
    mode: str,
    stakes: str,
    advisors: List[AdvisorResult],
    skipped_keys: List[str],
    peer_reviews: List[PeerReviewResult],
) -> str:
    convened = ", ".join(f"{a.persona.title} ({_model_label(a.persona)})" for a in advisors) or "none"
    skipped = ", ".join(skipped_keys) or "none"
    peer = "yes" if peer_reviews else "no"
    return (
        f"_Mode: {mode.upper()} | stakes: {stakes} | peer review: {peer}_\n"
        f"_Convened: {convened}_\n"
        f"_Skipped: {skipped}_"
    )


def _fallback_digest(advisors: List[AdvisorResult], peer_reviews: List[PeerReviewResult]) -> str:
    blocks: List[str] = []
    for advisor in advisors:
        if advisor.outcome.ok:
            blocks.append(f"#### {advisor.persona.title} ({advisor.persona.model})\n{advisor.outcome.text.strip()}")
    if peer_reviews:
        usable = [p for p in peer_reviews if p.outcome.ok]
        if usable:
            blocks.append(
                "#### Peer reviews\n"
                + "\n\n".join(f"- ({p.reviewer_model}) {p.outcome.text.strip()}" for p in usable)
            )
    return "\n\n".join(blocks) if blocks else "(no usable advisor responses)"
