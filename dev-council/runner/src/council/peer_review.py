"""Anonymized peer review.

Advisor responses are shuffled and relabeled A/B/C... so reviewers judge on
merit, not role. Each reviewer runs on a model from a DIFFERENT family than the
advisor it is paired with, so one family never both writes and grades the same
dominant finding. Reviewers run concurrently under one async bridge.
"""

from __future__ import annotations

import random
from string import ascii_uppercase
from typing import Dict, List, Optional

from council.backends import BackendRegistry, BackendTask
from council.input import AdvisorResult, PeerReviewResult
from council.metering import MeteringSink
from council.prompts import build_peer_review_prompt


def anonymize(advisors: List[AdvisorResult], rng: Optional[random.Random] = None) -> Dict[str, AdvisorResult]:
    """Return an ordered {letter: advisor} map over advisors with usable output."""

    usable = [a for a in advisors if a.outcome.ok]
    rng = rng or random.Random()
    shuffled = usable[:]
    rng.shuffle(shuffled)
    return {ascii_uppercase[i]: advisor for i, advisor in enumerate(shuffled)}


def _pick_reviewer_model(advisor_family: str, pool: Dict[str, str], default_model: str) -> tuple[str, str]:
    """Choose a (model, family) from a family different than the advisor's."""

    candidates = [(fam, model) for fam, model in pool.items() if fam != advisor_family and model]
    if candidates:
        family, model = candidates[0]
        return model, family
    if pool:
        family, model = next(iter(pool.items()))
        return model, family
    return default_model, advisor_family


def run_peer_review(
    advisors: List[AdvisorResult],
    brief: str,
    mode: str,
    cwd: str,
    peer_review_pool: Dict[str, str],
    default_model: str,
    meter: MeteringSink,
    registry: BackendRegistry,
    peer_review_backend: str = "cursor",
    rng: Optional[random.Random] = None,
) -> List[PeerReviewResult]:
    anonymized = anonymize(advisors, rng=rng)
    if len(anonymized) < 2:
        # Peer review needs at least two responses to be meaningful.
        return []

    anonymized_text = {letter: advisor.outcome.text.strip() for letter, advisor in anonymized.items()}
    prompt = build_peer_review_prompt(brief, mode, anonymized_text)

    # One reviewer per advisor, each on a family different from that advisor.
    review_specs = []
    for advisor in anonymized.values():
        model, family = _pick_reviewer_model(advisor.persona.family, peer_review_pool, default_model)
        review_specs.append((advisor.persona.key, model, family))

    backend = registry.get(peer_review_backend)
    tasks = [
        BackendTask(task_id=reviewer_for_key, prompt=prompt, model=model)
        for (reviewer_for_key, model, _family) in review_specs
    ]
    outcomes = backend.run_batch(tasks, cwd=cwd)

    results: List[PeerReviewResult] = []
    for (reviewer_for_key, model, family), outcome in zip(review_specs, outcomes):
        meter.record("peer", reviewer_for_key, model, family, outcome, backend=peer_review_backend)
        results.append(
            PeerReviewResult(
                reviewer_for_key=reviewer_for_key,
                reviewer_model=model,
                reviewer_family=family,
                outcome=outcome,
            )
        )
    return results
