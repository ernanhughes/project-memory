"""Staged admissibility gate. All three legs present, each traceable,
expected leg never inferred, current leg fresh, no cancelling evidence.

Stages:
  S0 three legs present (current, expected, difference text)
  S1 each cited leg traceable to a raw artifact
  S2 expected-state leg is stated, not itself inferred
  S3 current-state leg fresh as of the standpoint time
  S4 no cancelling evidence (contract, deferral, intentional preservation)

Reason codes are records of the algorithm's path, never post-hoc prose.
"""

from __future__ import annotations

from datetime import date

from .fixtures import TRACEABLE
from .model import (
    DerivedCandidate,
    GateDecision,
    ScopeTask,
    FRESHNESS_DAYS,
)


def _age_days(observed: str, standpoint: str) -> int:
    return (date.fromisoformat(standpoint)
            - date.fromisoformat(observed)).days


def check_candidate(candidate: DerivedCandidate, standpoint: str,
                    skip_current: bool = False,
                    skip_expected: bool = False,
                    skip_cancelling: bool = False) -> GateDecision:
    """Apply the staged gate to one candidate.

    The skip_* flags implement ablations only; the full gate uses none.
    """
    cid = candidate.candidate_id
    # S0: three legs present.
    if (candidate.current is None or candidate.expected is None
            or not candidate.difference.strip()):
        return GateDecision(cid, False, "S0",
                            "missing current, expected, or difference leg",
                            ())
    # S1: traceability.
    if (not candidate.current.traceable
            or candidate.current.artifact_id not in TRACEABLE
            or not candidate.expected.traceable
            or candidate.expected.artifact_id not in TRACEABLE):
        return GateDecision(cid, False, "S1",
                            "leg not traceable to a raw artifact", ())
    # S2: expected leg must be stated, never inferred.
    if not skip_expected and candidate.expected.inferred:
        return GateDecision(cid, False, "S2",
                            "expected-state leg is itself inferred",
                            (candidate.current.artifact_id,))
    # S3: current leg fresh as of standpoint.
    if not skip_current:
        try:
            age = _age_days(candidate.current.observed_at, standpoint)
        except ValueError:
            return GateDecision(cid, False, "S3",
                                "unparseable current-state date", ())
        if age < 0 or age > FRESHNESS_DAYS:
            return GateDecision(cid, False, "S3",
                                f"current-state leg stale: observed "
                                f"{candidate.current.observed_at}, "
                                f"standpoint {standpoint}",
                                (candidate.current.artifact_id,
                                 candidate.expected.artifact_id))
    # S4: no cancelling evidence.
    if not skip_cancelling and candidate.cancelling:
        kinds = ",".join(sorted(c.kind for c in candidate.cancelling))
        return GateDecision(cid, False, "S4",
                            f"cancelled by {kinds}: "
                            + "; ".join(c.artifact_id
                                        for c in candidate.cancelling),
                            (candidate.current.artifact_id,
                             candidate.expected.artifact_id))
    return GateDecision(cid, True, None, "all three legs cited, none "
                        "cancelled",
                        (candidate.current.artifact_id,
                         candidate.expected.artifact_id))


def apply_gate(task: ScopeTask, skip_current: bool = False,
               skip_expected: bool = False,
               skip_cancelling: bool = False) -> list[GateDecision]:
    return [check_candidate(c, task.standpoint, skip_current,
                            skip_expected, skip_cancelling)
            for c in task.candidates]
