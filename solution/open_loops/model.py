"""Expectation model: the smallest useful representation of an open loop.

Fields earn their place: identity, the desired transition (declarative,
serializable, versioned — never executable code), opening evidence with
derivation provenance, and optional deadline/trigger bounds. No owner,
priority, points, or workflow state: this is memory, not project
management.

Status vocabulary: OPEN / SATISFIED / CANCELLED / SUPERSEDED.
UNRESOLVED is computed (OPEN with no valid closing transition as of T),
never stored. UNKNOWN marks insufficient evidence/history.
"""

from __future__ import annotations

from dataclasses import dataclass, field


EXPECTATION_SCHEMA_VERSION = "open-loop-expectation-v0.1"


@dataclass(frozen=True)
class ExpectedTransition:
    """Declarative completion condition: subject predicate target.

    Supported predicates in v0.1: "equals" (subject state becomes target).
    Deterministic, serializable, versioned. No eval.
    """
    subject: str
    predicate: str = "equals"
    target: str = ""

    def to_dict(self) -> dict:
        return {"subject": self.subject, "predicate": self.predicate,
                "target": self.target}

    @classmethod
    def from_dict(cls, raw: dict) -> "ExpectedTransition":
        return cls(subject=raw["subject"],
                   predicate=raw.get("predicate", "equals"),
                   target=raw.get("target", ""))


@dataclass(frozen=True)
class Expectation:
    expectation_id: str
    subject: str
    desired: ExpectedTransition
    opened_at: str  # ISO-8601 event time of the opening
    opening_evidence: tuple[str, ...]  # event/artifact IDs (Ch7 refs)
    statement: str = ""  # opening utterance text (semantic-closure match)
    derivation: str = "oracle-labelled"  # or "ledger-established"
    required_before: str | None = None  # deadline artifact/event id
    trigger: str | None = None  # event-triggered obligation source
    scope: str = "project"
    schema_version: str = EXPECTATION_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "expectation_id": self.expectation_id,
            "subject": self.subject,
            "desired": self.desired.to_dict(),
            "opened_at": self.opened_at,
            "opening_evidence": list(self.opening_evidence),
            "statement": self.statement,
            "derivation": self.derivation,
            "required_before": self.required_before,
            "trigger": self.trigger,
            "scope": self.scope,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Expectation":
        return cls(
            expectation_id=raw["expectation_id"],
            subject=raw["subject"],
            desired=ExpectedTransition.from_dict(raw["desired"]),
            opened_at=raw["opened_at"],
            opening_evidence=tuple(raw.get("opening_evidence", ())),
            statement=raw.get("statement", ""),
            derivation=raw.get("derivation", "oracle-labelled"),
            required_before=raw.get("required_before"),
            trigger=raw.get("trigger"),
            scope=raw.get("scope", "project"),
            schema_version=raw.get("schema_version",
                                   EXPECTATION_SCHEMA_VERSION),
        )


@dataclass
class SearchFootprint:
    """What was actually checked before declaring something unresolved.

    Auditable absence accounting: searched channels, scope bound, candidate
    closures examined, and history gaps encountered. No probabilities.
    """
    expectation_id: str
    searched_sources: tuple[str, ...] = ()
    searched_until: str | None = None
    candidate_closures_examined: int = 0
    gaps: tuple[str, ...] = ()
    current_state_checked: bool = False

    def coverage(self, expected: tuple[str, ...]) -> str:
        have = sum(1 for channel in expected if channel in self.searched_sources)
        return f"{have}/{len(expected)} expected evidence channels"

    def to_dict(self) -> dict:
        return {
            "expectation_id": self.expectation_id,
            "searched_sources": list(self.searched_sources),
            "searched_until": self.searched_until,
            "candidate_closures_examined": self.candidate_closures_examined,
            "gaps": list(self.gaps),
            "current_state_checked": self.current_state_checked,
        }


@dataclass
class StatusReport:
    """A status verdict with its evidence (status and evidence kept apart)."""
    expectation_id: str
    status: str  # OPEN | SATISFIED | CANCELLED | SUPERSEDED | UNKNOWN
    confidence_class: str = ""  # CORROBORATED_OPEN | INCOMPLETE_SEARCH | ...
    opening_evidence: tuple[str, ...] = ()
    closing_evidence: tuple[str, ...] = ()
    closure_tier: str = ""  # state-transition | explicit | semantic | textual
    footprint: SearchFootprint | None = None
    deadline_passed: bool = False
    last_verified_at: str | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "expectation_id": self.expectation_id,
            "status": self.status,
            "confidence_class": self.confidence_class,
            "opening_evidence": list(self.opening_evidence),
            "closing_evidence": list(self.closing_evidence),
            "closure_tier": self.closure_tier,
            "footprint": self.footprint.to_dict() if self.footprint else None,
            "deadline_passed": self.deadline_passed,
            "last_verified_at": self.last_verified_at,
            "detail": self.detail,
        }
