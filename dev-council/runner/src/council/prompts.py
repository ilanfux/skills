"""Prompt templates for advisors, peer reviewers, and the Chairman.

These mirror the dev-council skill so the standalone runner produces the same
evidence-grounded, anonymized, peer-reviewed output.
"""

from __future__ import annotations

from typing import Dict, List

from council.input import AdvisorResult, PersonaSpec

_ADVISOR_TEMPLATE = """You are the {title} on a Dev Council reviewing engineering work.

Your lens: {lens}

The brief:
---
{brief}
---

Mode: {mode}
{grounding}
Rules:
{read_rule}
- Back every claim with evidence: cite path:line or a specific function/contract.
- Lean fully into your lens. Do NOT hedge or try to be balanced - other advisors cover the angles you don't. Synthesis comes later.
- If this change genuinely doesn't touch your domain, say so in ONE line and stop. Don't manufacture concerns.
- If a candidate finding is a documented intentional decision (per the brief's rules), do NOT flag it as a defect - label it "by design (per <source>)" and move on.
- 150-300 words. No preamble. Be concrete and specific to THIS code/decision.
{review_line}"""

_REVIEW_SCOPE_LINE = (
    "- Flag issues only on lines that were CHANGED (use git diff). Label each finding Critical / Major / Minor."
)

_PEER_REVIEW_TEMPLATE = """{n} advisors independently analyzed this engineering {decision_or_change}:
---
{brief}
---
Anonymized responses:
{anonymized}

Answer, referencing responses by letter, under 200 words:
1. Which response is strongest, and why?
2. Which has the biggest blind spot or weakest-supported claim? What is it missing?
3. What did ALL responses miss that the council must consider?"""

_CHAIRMAN_TEMPLATE = """You are the Chairman of a Dev Council. You receive the brief, every advisor's
de-anonymized analysis, and every peer review. Make the decisive call.

You are decisive: give a real recommendation, not "it depends". You may overrule
the majority when a dissenter's evidence is stronger. Stay grounded in the cited
evidence; do not invent findings.

The brief:
---
{brief}
---

Advisor analyses (de-anonymized):
{advisor_block}

Peer reviews:
{peer_block}

Produce the verdict in GitHub-flavored markdown, no preamble, using EXACTLY this structure:

{verdict_skeleton}"""

_PLAN_SKELETON = """## Council Verdict (Plan): <topic>
_Convened: <advisors> - skipped: <specialists + why>_

### Where the council agrees
<high-confidence points multiple advisors converged on, independently>

### Where the council clashes
<genuine disagreements - present both sides + why each is reasonable>

### Blind spots the council caught
<things that only surfaced in peer review>

### The recommendation
<a clear, decisive call with reasoning - not "it depends">

### The one thing to do first
<a single concrete next step>"""

_REVIEW_SKELETON = """## Council Verdict (Review): <what changed>
_Convened: <reviewers> - skipped: <specialists + why>_

### Must fix before merge (blocking)
- <finding> - `path:line` - why it matters

### Should fix (non-blocking)
- <finding> - `path:line`

### Where reviewers disagreed
<the call, with reasoning>

### What everyone missed
<surfaced in peer review>

### Verdict
<SHIP | FIX-THEN-SHIP | RETHINK> - one-line justification"""


def build_advisor_prompt(
    persona: PersonaSpec,
    brief: str,
    mode: str,
    diff_scope: str | None,
    repo_context: str | None = None,
    grounded: bool = True,
) -> str:
    """Build the advisor prompt.

    `grounded` backends (Cursor) browse the repo, so we tell the agent to read it.
    Non-grounded (provider) backends get `repo_context` injected as their only
    evidence and are told to cite strictly from it.
    """

    review_line = _REVIEW_SCOPE_LINE if mode == "review" else ""
    if grounded:
        grounding = "Working directory: the repository you can read with your tools."
        if diff_scope:
            grounding += f"\nDiff scope: {diff_scope}"
        read_rule = "- Read the actual code before forming any opinion (read/grep/glob the repo)."
    else:
        grounding = (repo_context or "").strip() or "(no repository context was available)"
        read_rule = (
            "- Base your analysis strictly on the evidence above; cite path:line from it. "
            "Do not invent or assume code you cannot see."
        )
    return _ADVISOR_TEMPLATE.format(
        title=persona.title,
        lens=persona.lens,
        brief=brief,
        mode=mode.upper(),
        grounding=grounding,
        read_rule=read_rule,
        review_line=review_line,
    )


def build_peer_review_prompt(brief: str, mode: str, anonymized_map: Dict[str, str]) -> str:
    decision_or_change = "decision" if mode == "plan" else "change"
    anonymized = "\n\n".join(f"**{letter}:** {text}" for letter, text in anonymized_map.items())
    return _PEER_REVIEW_TEMPLATE.format(
        n=len(anonymized_map),
        decision_or_change=decision_or_change,
        brief=brief,
        anonymized=anonymized,
    )


def build_chairman_prompt(
    brief: str,
    mode: str,
    advisors: List[AdvisorResult],
    peer_reviews: List[str],
) -> str:
    advisor_block = "\n\n".join(
        f"### {a.persona.title} (model: {a.persona.model})\n{a.outcome.text.strip()}"
        for a in advisors
        if a.outcome.ok
    )
    peer_block = (
        "\n\n".join(f"- {text.strip()}" for text in peer_reviews if text.strip())
        if peer_reviews
        else "(peer review not run for this tier)"
    )
    skeleton = _PLAN_SKELETON if mode == "plan" else _REVIEW_SKELETON
    return _CHAIRMAN_TEMPLATE.format(
        brief=brief,
        advisor_block=advisor_block or "(no advisor produced a usable response)",
        peer_block=peer_block,
        verdict_skeleton=skeleton,
    )
