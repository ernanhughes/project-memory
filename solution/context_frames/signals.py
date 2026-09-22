"""Separated selection signals.

Every signal is computed from metadata owned by an earlier layer, and
every one is recorded on the candidate. Nothing is collapsed into a
single learned importance number: the whole point of the layer is that a
bad bundle can be attributed to a component rather than to a scalar.

* ``query_relevance``    -- Chapter 3 fused retrieval score, normalised
* ``project_relevance``  -- ProjectFrame scope
* ``goal_relevance``     -- WorkFrame work type against the project's
                            evidence preferences, plus objective overlap
* ``temporal_validity``  -- Chapter 8 supersession as of the frame time
* ``evidence_strength``  -- Chapter 7 role: support, echo, refutation
* ``open_loop_relevance``-- Chapter 9 expectation attached to the unit
* ``relational_relevance`` -- Chapter 4/5 neighbourhood of admitted units
* ``recency``            -- freshness, a signal and never a rule
* ``redundancy``         -- overlap with what is already admitted
"""

from __future__ import annotations

from .corpus import K_OPEN_LOOP
from .model import MemoryUnit, ProjectFrame, WorkFrame
from .retrieval import tokenise

ABSENT_TIER = 99


def normalise_ranked(ranked: list[tuple[str, float]]) -> dict[str, float]:
    """Map fused retrieval scores onto [0, 1] by rank position."""
    if not ranked:
        return {}
    n = len(ranked)
    return {unit_id: 1.0 - (i / n) for i, (unit_id, _) in enumerate(ranked)}


def goal_tier(unit: MemoryUnit, frame: ProjectFrame,
              work_type: str) -> int:
    prefs = frame.preferences_for(work_type)
    if unit.kind in prefs:
        return prefs.index(unit.kind)
    return ABSENT_TIER


def goal_relevance(unit: MemoryUnit, frame: ProjectFrame,
                   work: WorkFrame) -> float:
    """Class preference for the work type, lifted by objective overlap.

    The class term is the project's standing policy; the overlap term is
    the only part that varies with the particular objective text.
    """
    prefs = frame.preferences_for(work.work_type)
    tier = goal_tier(unit, frame, work.work_type)
    class_term = 0.0 if tier == ABSENT_TIER else 1.0 - (tier / max(len(prefs), 1))
    terms = work.objective_terms()
    if terms:
        unit_terms = set(tokenise(unit.text))
        overlap = len(terms & unit_terms) / len(terms)
    else:
        overlap = 0.0
    return round(0.75 * class_term + 0.25 * min(overlap * 2.0, 1.0), 4)


def temporal_validity(unit: MemoryUnit, as_of: str) -> float:
    """Chapter 8: a superseded unit is still history, not current evidence."""
    if unit.is_current(as_of):
        return 1.0
    return 0.25


def evidence_strength(unit: MemoryUnit) -> float:
    """Chapter 7: restatement is not corroboration; refutation is kept."""
    if unit.evidence_role == "echo":
        return 0.35
    if unit.evidence_role == "refutes":
        return 0.9
    if unit.evidence_role == "none":
        return 0.5
    return 1.0


def open_loop_relevance(unit: MemoryUnit, frame: ProjectFrame,
                        work: WorkFrame) -> float:
    """Chapter 9 material matters when the work type makes it matter."""
    if unit.open_loop is None and unit.kind != K_OPEN_LOOP:
        return 0.0
    prefs = frame.preferences_for(work.work_type)
    if K_OPEN_LOOP not in prefs:
        return 0.0
    return 1.0 - (prefs.index(K_OPEN_LOOP) / max(len(prefs), 1))


def recency(unit: MemoryUnit, as_of: str) -> float:
    """Newer is higher. Reported, never decisive on its own."""
    if not unit.event_time:
        return 0.0
    return 1.0 if unit.event_time[:10] >= as_of[:10] else _decay(
        unit.event_time[:10], as_of[:10])


def _decay(event_day: str, as_of_day: str) -> float:
    from datetime import date
    try:
        a = date.fromisoformat(event_day)
        b = date.fromisoformat(as_of_day)
    except ValueError:
        return 0.0
    days = max((b - a).days, 0)
    return round(1.0 / (1.0 + days / 30.0), 4)


def relational_relevance(unit: MemoryUnit, anchors: set[str]) -> float:
    """Chapter 4/5 adjacency to already-selected evidence."""
    if not unit.related or not anchors:
        return 0.0
    hits = len(set(unit.related) & anchors)
    return round(min(hits / len(unit.related), 1.0), 4)


def redundancy(unit: MemoryUnit, admitted: list[MemoryUnit]) -> float:
    """Token-set overlap with the best-matching admitted unit."""
    if not admitted:
        return 0.0
    mine = set(tokenise(unit.text))
    if not mine:
        return 0.0
    best = 0.0
    for other in admitted:
        theirs = set(tokenise(other.text))
        if not theirs:
            continue
        best = max(best, len(mine & theirs) / len(mine | theirs))
    return round(best, 4)
