"""Knowing when enough is enough.

A controller that can escalate must also be able to stop, and stopping is
exactly as consequential as routing: stopping too early is under-routing,
stopping too late is over-routing, and only measuring both keeps a
sequential policy honest.

The stop rule reads diagnostics, not confidence alone. A reader's
self-reported confidence is one signal among several and not obviously
the best one, so the rule combines evidence presence, score margin, and
provenance availability, and the chapter measures each signal's
contribution rather than assuming the model knows when it is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StopDecision:
    stop: bool
    reason: str
    signals: dict


@dataclass(frozen=True)
class StopConfig:
    """Thresholds, stated so they can be swept rather than defended."""

    min_evidence: int = 1
    min_top_score: float = 0.0
    require_provenance: bool = True
    # Below this margin between the best and second-best candidate, the
    # retrieval is treated as unsettled even if something came back.
    min_margin: float = 0.0
    version: str = "nexus-stop-v0.1"


def should_stop(
    observations, config: StopConfig, budget_exhausted: bool = False
) -> StopDecision:
    """Decide whether the episode has enough to answer."""
    if budget_exhausted:
        return StopDecision(True, "budget-exhausted", {})
    if not observations:
        return StopDecision(False, "nothing-tried", {})
    last = observations[-1]
    signals = {
        "evidence_count": last.evidence_count,
        "top_score": round(last.top_score, 4),
        "score_margin": round(last.score_margin, 4),
        "provenance_available": last.provenance_available,
        "abstained": last.abstained,
    }
    if last.abstained or last.evidence_count < config.min_evidence:
        return StopDecision(False, "no-evidence-returned", signals)
    if config.require_provenance and not last.provenance_available:
        return StopDecision(False, "no-provenance", signals)
    if last.top_score < config.min_top_score:
        return StopDecision(False, "weak-top-score", signals)
    if config.min_margin > 0.0 and last.score_margin < config.min_margin:
        return StopDecision(False, "unsettled-ranking", signals)
    return StopDecision(True, "sufficient-evidence", signals)


def detect_disagreement(observations) -> tuple[bool, str]:
    """Do two capabilities point at materially different source sets?

    Disagreement between cheap mechanisms is a candidate escalation
    signal that does not depend on any model's self-assessment. Chapter 6
    only has to decide that a disagreement deserves attention; resolving
    the contradiction is Chapter 8's problem.
    """
    with_sources = [
        observation for observation in observations
        if observation.source_ids
    ]
    if len(with_sources) < 2:
        return False, ""
    first = set(with_sources[-2].source_ids)
    second = set(with_sources[-1].source_ids)
    if not first or not second:
        return False, ""
    overlap = len(first & second) / len(first | second)
    if overlap < 0.34:
        return True, (
            f"{with_sources[-2].capability_id} and "
            f"{with_sources[-1].capability_id} agree on "
            f"{overlap:.0%} of their sources"
        )
    return False, ""
