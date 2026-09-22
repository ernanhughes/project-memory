"""Model: legs, candidates, gate decisions, scope tasks.

No confidence scalar in v1. A candidate is admissible only when every
staged check passes. The trace records the real decision path; nothing
is explained by a model after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

GATE_VERSION = "staged-triple-gate-v1"
SCHEMA_VERSION = "derived-loop-v1"
STANDPOINT = "2025-02-07"  # task-108 compatibility-release standpoint
FRESHNESS_DAYS = 60  # current-state leg must be this fresh vs standpoint


@dataclass(frozen=True)
class Leg:
    kind: str  # "current" | "expected"
    artifact_id: str  # raw artifact or snapshot id; must be traceable
    statement: str
    observed_at: str  # ISO date of the evidence
    inferred: bool = False  # True when the leg is itself inferred
    traceable: bool = True  # False simulates untraceable provenance


@dataclass(frozen=True)
class CancellingEvidence:
    kind: str  # "contract" | "intentional-preservation" | "deferral"
    artifact_id: str
    statement: str


@dataclass(frozen=True)
class DerivedCandidate:
    candidate_id: str
    subject: str
    difference: str
    current: Leg | None
    expected: Leg | None
    cancelling: tuple[CancellingEvidence, ...] = ()
    # Ledger-only fields, never visible to the gate at runtime:
    ledger_genuine: bool = False
    ledger_harmful_if_acted: bool = False

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "subject": self.subject,
            "difference": self.difference,
            "current": None if self.current is None else {
                "kind": self.current.kind,
                "artifact_id": self.current.artifact_id,
                "statement": self.current.statement,
                "observed_at": self.current.observed_at,
                "inferred": self.current.inferred,
                "traceable": self.current.traceable},
            "expected": None if self.expected is None else {
                "kind": self.expected.kind,
                "artifact_id": self.expected.artifact_id,
                "statement": self.expected.statement,
                "observed_at": self.expected.observed_at,
                "inferred": self.expected.inferred,
                "traceable": self.expected.traceable},
            "cancelling": [{"kind": c.kind, "artifact_id": c.artifact_id,
                            "statement": c.statement}
                           for c in self.cancelling],
        }


@dataclass(frozen=True)
class GateDecision:
    candidate_id: str
    admitted: bool
    stage_failed: str | None  # None when admitted; S0..S4 otherwise
    reason: str
    legs_cited: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"candidate_id": self.candidate_id,
                "admitted": self.admitted,
                "stage_failed": self.stage_failed,
                "reason": self.reason,
                "legs_cited": list(self.legs_cited)}


@dataclass(frozen=True)
class ScopeTask:
    task_id: str
    scope: str
    standpoint: str = STANDPOINT
    candidates: tuple[DerivedCandidate, ...] = ()
    # Explicit (stated) obligations in this scope; the derived scorer
    # must not claim them as derived.
    explicit_obligations: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"task_id": self.task_id, "scope": self.scope,
                "standpoint": self.standpoint,
                "explicit_obligations": list(self.explicit_obligations),
                "candidates": [c.to_dict() for c in self.candidates]}
