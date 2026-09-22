"""Frame objects: the durable project lens, the ephemeral work lens,
the bounded bundle handed to the model, and the trace that explains it.

Four types, each with one job:

* ``ProjectFrame`` -- relatively durable, versioned, human-authored policy
  describing what generally matters in a project. Configuration, not
  context. It never contains the current request.
* ``WorkFrame`` -- ephemeral, evidence-backed description of the work
  being done now. Built from ``WorkSignal`` objects, which may be a user
  message, an event, a tool result, a failing test, or a scheduled job.
  Nothing here depends on there being a prompt.
* ``ContextBundle`` -- the exact bounded evidence admitted to the model.
* ``ContextTrace`` -- why every candidate was admitted or rejected, under
  which frames and which policy version.

No field holds an intrinsic ``priority``. Importance is computed against
a frame and recorded in the trace; it is never stored on the memory.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

PROJECT_FRAME_SCHEMA = "project-frame/v0.1"
WORK_FRAME_SCHEMA = "work-frame/v0.1"
BUNDLE_SCHEMA = "context-bundle/v0.1"
TRACE_SCHEMA = "context-trace/v0.1"

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Characters/4, labelled an estimate wherever it is reported (Ch3)."""
    return max(1, len(text) // CHARS_PER_TOKEN)


# --------------------------------------------------------------------------
# Memory units: the common envelope every source layer is normalised into.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryUnit:
    """One retrievable piece of remembered history.

    Metadata is carried from the layer that owns it: ``kind`` is a corpus
    fact, ``valid_until``/``superseded_by`` come from Chapter 8, evidence
    role and ``echo_of`` from Chapter 7, ``open_loop`` from Chapter 9.
    None of it is task-specific labelling.
    """
    unit_id: str
    project_id: str
    kind: str                       # evidence class: result, baseline, prose
    text: str
    source_refs: tuple[str, ...] = ()
    event_time: str = ""
    valid_from: str = ""
    valid_until: str | None = None  # Ch8: superseded at this time
    superseded_by: str | None = None
    evidence_role: str = "support"  # support | echo | refutes | none (Ch7)
    echo_of: str | None = None
    claim_key: str = ""             # coalescing group (Ch7 support group)
    open_loop: str | None = None    # Ch9 expectation id, if any
    related: tuple[str, ...] = ()   # Ch4/5 graph/associative neighbours

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)

    def is_current(self, as_of: str) -> bool:
        return self.valid_until is None or as_of < self.valid_until

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id, "project_id": self.project_id,
            "kind": self.kind, "source_refs": list(self.source_refs),
            "event_time": self.event_time, "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "superseded_by": self.superseded_by,
            "evidence_role": self.evidence_role, "echo_of": self.echo_of,
            "claim_key": self.claim_key, "open_loop": self.open_loop,
            "tokens": self.tokens,
        }


# --------------------------------------------------------------------------
# ProjectFrame -- durable configuration.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ProjectFrame:
    project_id: str
    version: str
    purpose: str = ""
    objectives: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    include_projects: tuple[str, ...] = ()
    # work_type -> ordered evidence classes, most useful first.
    evidence_preferences: tuple[tuple[str, tuple[str, ...]], ...] = ()
    preserve_conflicts: bool = True
    penalise_stale: bool = True
    require_provenance: bool = True
    # How many candidates each preferred class is guaranteed in the pool.
    # A policy constant, versioned with the frame like any other.
    class_pull_width: int = 3
    schema_version: str = PROJECT_FRAME_SCHEMA

    def scope(self) -> tuple[str, ...]:
        return self.include_projects or (self.project_id,)

    def preferences_for(self, work_type: str) -> tuple[str, ...]:
        table = dict(self.evidence_preferences)
        return table.get(work_type, table.get("default", ()))

    def known_work_types(self) -> tuple[str, ...]:
        return tuple(k for k, _ in self.evidence_preferences if k != "default")

    def frame_id(self) -> str:
        return f"{self.project_id}-{self.version}"

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id, "version": self.version,
            "purpose": self.purpose, "objectives": list(self.objectives),
            "constraints": list(self.constraints),
            "include_projects": list(self.include_projects),
            "evidence_preferences": {k: list(v)
                                     for k, v in self.evidence_preferences},
            "preserve_conflicts": self.preserve_conflicts,
            "penalise_stale": self.penalise_stale,
            "require_provenance": self.require_provenance,
            "class_pull_width": self.class_pull_width,
            "schema_version": self.schema_version,
        }


# --------------------------------------------------------------------------
# WorkSignal / WorkFrame -- the current situation, with provenance.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkSignal:
    """One observation that contributes to the current work frame.

    ``kind`` names the channel: user_message, event, tool_result,
    test_failure, scheduled_job, agent_task, project_state. The frame
    builder cites these; a WorkFrame field with no signal behind it is a
    guess, and the schema makes that visible.
    """
    signal_id: str
    kind: str
    text: str
    observed_at: str = ""

    def to_dict(self) -> dict:
        return {"signal_id": self.signal_id, "kind": self.kind,
                "text": self.text, "observed_at": self.observed_at}


@dataclass(frozen=True)
class WorkFrame:
    work_frame_id: str
    project_id: str
    objective: str
    work_type: str
    as_of: str
    active_constraints: tuple[str, ...] = ()
    signals: tuple[WorkSignal, ...] = ()
    # field -> signal ids that licensed it
    provenance: tuple[tuple[str, tuple[str, ...]], ...] = ()
    derivation: str = "declared"   # declared | inferred
    schema_version: str = WORK_FRAME_SCHEMA

    def objective_terms(self) -> set[str]:
        return {t for t in re.findall(r"[a-z0-9]+", self.objective.lower())
                if len(t) > 2}

    def unprovenanced_fields(self) -> tuple[str, ...]:
        have = {k for k, refs in self.provenance if refs}
        return tuple(f for f in ("objective", "work_type") if f not in have)

    def to_dict(self) -> dict:
        return {
            "work_frame_id": self.work_frame_id, "project_id": self.project_id,
            "objective": self.objective, "work_type": self.work_type,
            "as_of": self.as_of,
            "active_constraints": list(self.active_constraints),
            "signals": [s.to_dict() for s in self.signals],
            "provenance": {k: list(v) for k, v in self.provenance},
            "derivation": self.derivation,
            "schema_version": self.schema_version,
        }


# --------------------------------------------------------------------------
# Candidates, signals, decisions.
# --------------------------------------------------------------------------

@dataclass
class Signals:
    """Separated score components. Never collapsed into one stored number.

    Kept separate so a failure can be attributed to a component rather
    than to a scalar nobody can inspect.
    """
    query_relevance: float = 0.0
    goal_relevance: float = 0.0
    project_relevance: float = 0.0
    temporal_validity: float = 1.0
    evidence_strength: float = 0.0
    open_loop_relevance: float = 0.0
    relational_relevance: float = 0.0
    recency: float = 0.0
    redundancy: float = 0.0

    def to_dict(self) -> dict:
        return {k: round(v, 4) for k, v in self.__dict__.items()}


@dataclass
class Candidate:
    unit: MemoryUnit
    retrieval_rank: int = 0
    signals: Signals = field(default_factory=Signals)
    stage_score: float = 0.0
    eligible: bool = True
    reason_codes: list[str] = field(default_factory=list)
    decision: str = "pending"       # admit | reject | pending
    coalesced_into: str | None = None

    @property
    def unit_id(self) -> str:
        return self.unit.unit_id

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.unit_id,
            "project_id": self.unit.project_id,
            "kind": self.unit.kind,
            "retrieval_rank": self.retrieval_rank,
            "eligible": self.eligible,
            "signals": self.signals.to_dict(),
            "stage_score": round(self.stage_score, 4),
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "coalesced_into": self.coalesced_into,
            "token_cost": self.unit.tokens,
            "source_refs": list(self.unit.source_refs),
        }


# --------------------------------------------------------------------------
# Bundle and trace.
# --------------------------------------------------------------------------

@dataclass
class BundleItem:
    """An admitted unit, or a coalesced group of units.

    A group keeps every member id and every source ref: coalescing may
    remove repetition, never provenance, disagreement, or a temporal
    boundary.
    """
    item_id: str
    text: str
    members: tuple[str, ...]
    source_refs: tuple[str, ...]
    kind: str
    claim_key: str = ""
    conflict_with: tuple[str, ...] = ()
    temporal_note: str = ""

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)

    def to_dict(self) -> dict:
        return {"item_id": self.item_id, "members": list(self.members),
                "source_refs": list(self.source_refs), "kind": self.kind,
                "claim_key": self.claim_key,
                "conflict_with": list(self.conflict_with),
                "temporal_note": self.temporal_note, "tokens": self.tokens}


@dataclass
class ContextBundle:
    bundle_id: str
    items: list[BundleItem] = field(default_factory=list)
    budget_tokens: int = 0
    condition: str = ""
    schema_version: str = BUNDLE_SCHEMA

    @property
    def tokens(self) -> int:
        return sum(i.tokens for i in self.items)

    def unit_ids(self) -> list[str]:
        out: list[str] = []
        for item in self.items:
            out.extend(item.members)
        return out

    def render(self) -> str:
        parts = []
        for item in self.items:
            refs = ", ".join(item.source_refs) or "unsourced"
            head = f"[{item.kind} | sources: {refs}]"
            if item.temporal_note:
                head += f"\n[temporal: {item.temporal_note}]"
            if item.conflict_with:
                head += f"\n[disagrees with: {', '.join(item.conflict_with)}]"
            parts.append(f"{head}\n{item.text}")
        return "\n\n---\n\n".join(parts)

    def digest(self) -> str:
        payload = json.dumps([i.to_dict() for i in self.items], sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {"bundle_id": self.bundle_id, "condition": self.condition,
                "budget_tokens": self.budget_tokens,
                "bundle_tokens": self.tokens,
                "bundle_digest": self.digest(),
                "items": [i.to_dict() for i in self.items],
                "schema_version": self.schema_version}


@dataclass
class ContextTrace:
    """The frozen account of one context construction.

    It answers both questions a bundle alone cannot: why did this memory
    enter, and why did that apparently relevant memory not?
    """
    trace_id: str
    condition: str
    policy_version: str
    project_frame: str
    work_frame: str
    query: str
    as_of: str
    budget_tokens: int
    candidates: list[Candidate] = field(default_factory=list)
    stages: list[dict] = field(default_factory=list)
    bundle_digest: str = ""
    bundle_tokens: int = 0
    latency_ms: float = 0.0
    retriever: str = ""
    schema_version: str = TRACE_SCHEMA

    def admitted(self) -> list[Candidate]:
        return [c for c in self.candidates if c.decision == "admit"]

    def rejected(self) -> list[Candidate]:
        return [c for c in self.candidates if c.decision == "reject"]

    def why(self, unit_id: str) -> dict | None:
        for c in self.candidates:
            if c.unit_id == unit_id:
                return c.to_dict()
        return None

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id, "condition": self.condition,
            "policy_version": self.policy_version,
            "project_frame": self.project_frame, "work_frame": self.work_frame,
            "query": self.query, "as_of": self.as_of,
            "budget_tokens": self.budget_tokens,
            "retriever": self.retriever,
            "candidate_count": len(self.candidates),
            "admitted_count": len(self.admitted()),
            "rejected_count": len(self.rejected()),
            "stages": self.stages,
            "bundle_digest": self.bundle_digest,
            "bundle_tokens": self.bundle_tokens,
            "latency_ms": round(self.latency_ms, 2),
            "candidates": [c.to_dict() for c in self.candidates],
            "schema_version": self.schema_version,
        }
