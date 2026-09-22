"""Metric observations and failure attribution.

A failed answer never produces a bare FAIL. Each observation carries the
metric, its value, the evidence behind it, and — where determinable — the
failure class that tells the experimenter which layer to repair.
"""

from __future__ import annotations

from dataclasses import dataclass


class FailureClass:
    """Diagnostic failure classes (first version, not frozen)."""

    NOT_STORED = "NOT_STORED"
    NOT_RETRIEVED = "NOT_RETRIEVED"
    WRONG_RETRIEVAL = "WRONG_RETRIEVAL"
    CORRECT_EVIDENCE_WRONG_INTERPRETATION = (
        "CORRECT_EVIDENCE_WRONG_INTERPRETATION"
    )
    PROPOSAL_AS_DECISION = "PROPOSAL_AS_DECISION"
    REJECTED_AS_ACCEPTED = "REJECTED_AS_ACCEPTED"
    STALE_STATE = "STALE_STATE"
    MISSED_SUPERSESSION = "MISSED_SUPERSESSION"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    FALSE_PROVENANCE = "FALSE_PROVENANCE"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    FAILED_ABSTENTION = "FAILED_ABSTENTION"
    UNNECESSARY_ABSTENTION = "UNNECESSARY_ABSTENTION"
    CONTEXT_OMISSION = "CONTEXT_OMISSION"
    CONTEXT_DISTRACTION = "CONTEXT_DISTRACTION"
    CORRECT_MEMORY_NOT_USED = "CORRECT_MEMORY_NOT_USED"
    HARMFUL_MEMORY = "HARMFUL_MEMORY"
    DOWNSTREAM_REASONING_FAILURE = "DOWNSTREAM_REASONING_FAILURE"
    EVALUATOR_DEFECT = "EVALUATOR_DEFECT"
    AMBIGUOUS_GROUND_TRUTH = "AMBIGUOUS_GROUND_TRUTH"


MECHANICAL = "mechanical"


@dataclass(frozen=True)
class MemoryObservation:
    """One scored fact about one task output."""

    task_id: str
    metric: str
    value: float | bool | str | None
    evidence: tuple[str, ...] = ()
    failure_class: str | None = None
    grader: str = MECHANICAL
    notes: str = ""

    @property
    def passed(self) -> bool | None:
        """Boolean verdict where the metric admits one, else None."""
        if isinstance(self.value, bool):
            return self.value
        return None
