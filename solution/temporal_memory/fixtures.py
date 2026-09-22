"""Deterministic fixtures for the E8 suite.

Running-example anchors reuse the book's frozen IDs (adr-007,
session-014, session-033, session-040, session-044, incident-021,
release-024) as evidence_refs / source provenance. New temporal event
IDs live under the ch8- namespace (solution fixture IDs, like the E7
claim-/span IDs); no ledger display artifact is invented.
"""

from __future__ import annotations

from .model import EventEnvelope

SUBJECT_BACKEND = "event-store.backend"
SUBJECT_FLAG = "feature-x.enabled"


def E(event_id: str, source_id: str, source_seq: int, event_type: str,
      subject: str, event_time: str, recorded_at: str, value: str = "",
      state_key: str = "", effective_from: str | None = None,
      effective_to: str | None = None,
      causal_parents: tuple[str, ...] = (),
      supersedes: tuple[str, ...] = (),
      corrects: tuple[str, ...] = (),
      evidence_refs: tuple[str, ...] = ()) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id, source_id=source_id, source_seq=source_seq,
        event_type=event_type, subject=subject, state_key=state_key,
        value=value, event_time=event_time, recorded_at=recorded_at,
        effective_from=effective_from, effective_to=effective_to,
        causal_parents=causal_parents, supersedes=supersedes,
        corrects=corrects, evidence_refs=evidence_refs)


def canonical_migration() -> list[EventEnvelope]:
    """A -> B -> C: benchmark, decision, deployment. Semantic order."""
    return [
        E("ch8-sqlite-current", "ledger", 1, "FACT_ESTABLISHED",
          SUBJECT_BACKEND, "2026-03-02T09:00:00Z", "2026-03-02T09:05:00Z",
          value="SQLite", state_key="backend"),
        E("ch8-contention", "session-014", 1, "OBSERVATION_RECORDED",
          SUBJECT_BACKEND, "2026-06-12T10:00:00Z", "2026-06-12T10:05:00Z",
          evidence_refs=("session-014",)),
        E("ch8-benchmark", "benchmark-svc", 1, "OBSERVATION_RECORDED",
          SUBJECT_BACKEND, "2026-06-19T10:00:00Z", "2026-06-19T10:05:00Z",
          evidence_refs=("session-019",)),
        E("ch8-decision", "decisions", 1, "DECISION_MADE",
          SUBJECT_BACKEND, "2026-06-25T14:00:00Z", "2026-06-25T14:05:00Z",
          value="PostgreSQL", state_key="backend",
          effective_from="2026-07-10T09:00:00Z",
          causal_parents=("ch8-benchmark", "ch8-contention"),
          evidence_refs=("adr-007", "session-033")),
        E("ch8-deploy", "deploy-svc", 1, "STATE_CHANGED",
          SUBJECT_BACKEND, "2026-07-10T09:00:00Z", "2026-07-10T09:05:00Z",
          value="PostgreSQL", state_key="backend",
          effective_from="2026-07-10T09:00:00Z",
          causal_parents=("ch8-decision",),
          evidence_refs=("adr-007",)),
        E("ch8-replicate", "session-044", 1, "OBSERVATION_RECORDED",
          SUBJECT_BACKEND, "2026-07-02T10:00:00Z", "2026-07-02T10:05:00Z",
          evidence_refs=("session-044",)),
    ]


def permuted_decision_first() -> list[EventEnvelope]:
    """Same contents, B -> A -> C: decision precedes the benchmark."""
    events = canonical_migration()
    by_id = {e.event_id: e for e in events}
    # Move decision before benchmark in event time; drop the benchmark
    # as a causal parent (it can corroborate, not motivate).
    swapped = []
    for e in events:
        if e.event_id == "ch8-decision":
            swapped.append(E(e.event_id, e.source_id, e.source_seq,
                             e.event_type, e.subject, "2026-06-10T14:00:00Z",
                             "2026-06-10T14:05:00Z", value=e.value,
                             state_key=e.state_key,
                             effective_from=e.effective_from,
                             causal_parents=("ch8-contention",),
                             evidence_refs=e.evidence_refs))
        elif e.event_id == "ch8-benchmark":
            swapped.append(E(e.event_id, e.source_id, e.source_seq,
                             e.event_type, e.subject, "2026-06-19T10:00:00Z",
                             "2026-06-19T10:05:00Z",
                             evidence_refs=e.evidence_refs))
        else:
            swapped.append(e)
    assert by_id  # keep mapping visible for readers
    return swapped


def invariant_pair() -> tuple[list[EventEnvelope], list[EventEnvelope]]:
    """Two independent events (README note, CSS fix); swap must not matter."""
    base = canonical_migration() + [
        E("ch8-readme", "docs-svc", 1, "OBSERVATION_RECORDED",
          "docs.readme", "2026-06-20T09:00:00Z", "2026-06-20T09:05:00Z",
          value="updated"),
        E("ch8-cssfix", "frontend-svc", 1, "OBSERVATION_RECORDED",
          "frontend.css", "2026-06-21T09:00:00Z", "2026-06-21T09:05:00Z",
          value="fixed"),
    ]
    swapped = []
    for e in base:
        if e.event_id == "ch8-readme":
            swapped.append(E(e.event_id, e.source_id, e.source_seq,
                             e.event_type, e.subject, "2026-06-21T09:00:00Z",
                             "2026-06-21T09:05:00Z", value=e.value))
        elif e.event_id == "ch8-cssfix":
            swapped.append(E(e.event_id, e.source_id, e.source_seq,
                             e.event_type, e.subject, "2026-06-20T09:00:00Z",
                             "2026-06-20T09:05:00Z", value=e.value))
        else:
            swapped.append(e)
    return base, swapped


def late_arrival() -> list[EventEnvelope]:
    """July 10 cutover learned August 3 (bitemporal gap)."""
    events = canonical_migration()
    out = []
    for e in events:
        if e.event_id == "ch8-deploy":
            out.append(E(e.event_id, e.source_id, e.source_seq,
                         e.event_type, e.subject, e.event_time,
                         "2026-08-03T09:00:00Z", value=e.value,
                         state_key=e.state_key,
                         effective_from=e.effective_from,
                         causal_parents=e.causal_parents,
                         evidence_refs=e.evidence_refs))
        else:
            out.append(e)
    return out


def future_effective() -> list[EventEnvelope]:
    """Sept 1 decision, effective on release-024 (Sept 15)."""
    return [
        E("ch8-fe-current", "ledger", 1, "FACT_ESTABLISHED",
          SUBJECT_BACKEND, "2026-08-01T09:00:00Z", "2026-08-01T09:05:00Z",
          value="SQLite", state_key="backend"),
        E("ch8-fe-decision", "decisions", 1, "DECISION_MADE",
          SUBJECT_BACKEND, "2026-09-01T10:00:00Z", "2026-09-01T10:05:00Z",
          value="PostgreSQL", state_key="backend",
          effective_from="2026-09-15T09:00:00Z",
          evidence_refs=("release-024",)),
        E("ch8-fe-release", "release-svc", 1, "STATE_CHANGED",
          SUBJECT_BACKEND, "2026-09-15T09:00:00Z", "2026-09-15T09:05:00Z",
          value="PostgreSQL", state_key="backend",
          effective_from="2026-09-15T09:00:00Z",
          causal_parents=("ch8-fe-decision",),
          evidence_refs=("release-024",)),
    ]


def correction_case() -> list[EventEnvelope]:
    """Benchmark misread; correction appends, history preserved."""
    return [
        E("ch8-c-bench", "benchmark-svc", 1, "OBSERVATION_RECORDED",
          SUBJECT_BACKEND, "2026-06-19T10:00:00Z", "2026-06-19T10:05:00Z",
          value="40x", state_key="speedup"),
        E("ch8-c-decision", "decisions", 1, "DECISION_MADE",
          SUBJECT_BACKEND, "2026-06-25T14:00:00Z", "2026-06-25T14:05:00Z",
          value="PostgreSQL", state_key="backend",
          effective_from="2026-07-10T09:00:00Z",
          causal_parents=("ch8-c-bench",),
          evidence_refs=("adr-007",)),
        E("ch8-c-correction", "benchmark-svc", 2, "CORRECTION_RECORDED",
          SUBJECT_BACKEND, "2026-07-05T10:00:00Z", "2026-07-05T10:05:00Z",
          value="35x", state_key="speedup",
          corrects=("ch8-c-bench",),
          evidence_refs=("session-044",)),
        E("ch8-c-deploy", "deploy-svc", 1, "STATE_CHANGED",
          SUBJECT_BACKEND, "2026-07-10T09:00:00Z", "2026-07-10T09:05:00Z",
          value="PostgreSQL", state_key="backend",
          effective_from="2026-07-10T09:00:00Z",
          causal_parents=("ch8-c-decision",)),
    ]


def revision_case() -> list[EventEnvelope]:
    """Revision changes endorsement going forward (contrast with correction)."""
    return [
        E("ch8-r-v1", "decisions", 1, "STATE_CHANGED",
          SUBJECT_BACKEND, "2026-05-01T09:00:00Z", "2026-05-01T09:05:00Z",
          value="SQLite", state_key="backend",
          effective_from="2026-05-01T09:00:00Z"),
        E("ch8-r-v2", "decisions", 2, "REVISION_MADE",
          SUBJECT_BACKEND, "2026-07-10T09:00:00Z", "2026-07-10T09:05:00Z",
          value="PostgreSQL", state_key="backend",
          effective_from="2026-07-10T09:00:00Z",
          supersedes=("ch8-r-v1",)),
    ]


def partial_order_case() -> list[EventEnvelope]:
    """A and B both precede C; A/B relative order unknown (equal stamps)."""
    return [
        E("ch8-p-a", "docs-svc", 1, "OBSERVATION_RECORDED",
          "docs.readme", "2026-06-20T09:00:00Z", "2026-06-20T09:01:00Z",
          value="updated"),
        E("ch8-p-b", "frontend-svc", 1, "OBSERVATION_RECORDED",
          "frontend.css", "2026-06-20T09:00:00Z", "2026-06-20T09:02:00Z",
          value="fixed"),
        E("ch8-p-c", "release-svc", 1, "STATE_CHANGED",
          SUBJECT_BACKEND, "2026-06-21T09:00:00Z", "2026-06-21T09:05:00Z",
          value="PostgreSQL", state_key="backend",
          effective_from="2026-06-21T09:00:00Z",
          causal_parents=("ch8-p-a", "ch8-p-b")),
    ]


def gap_stream() -> list[EventEnvelope]:
    """Source skips seq 18 (17 then 19): deterministic gap fixture."""
    return [
        E("ch8-g-17", "benchmark-svc", 17, "OBSERVATION_RECORDED",
          SUBJECT_BACKEND, "2026-06-19T10:00:00Z", "2026-06-19T10:05:00Z"),
        E("ch8-g-19", "benchmark-svc", 19, "OBSERVATION_RECORDED",
          SUBJECT_BACKEND, "2026-06-19T11:00:00Z", "2026-06-19T11:05:00Z"),
    ]


def second_domain() -> tuple[list[EventEnvelope], list[EventEnvelope]]:
    """Feature-flag incident: order decides whether the flag could have
    contributed. Precedence alone never proves causality (no causal edge
    is asserted from the incident to the flag)."""
    enabled_first = [
        E("ch8-f-on", "flag-svc", 1, "STATE_CHANGED",
          SUBJECT_FLAG, "2026-06-01T09:00:00Z", "2026-06-01T09:05:00Z",
          value="on", state_key="enabled",
          effective_from="2026-06-01T09:00:00Z"),
        E("ch8-f-incident", "incident-svc", 1, "OBSERVATION_RECORDED",
          "incident-026-like", "2026-06-05T09:00:00Z", "2026-06-05T09:05:00Z",
          value="outage"),
        E("ch8-f-off", "flag-svc", 2, "STATE_CHANGED",
          SUBJECT_FLAG, "2026-06-06T09:00:00Z", "2026-06-06T09:05:00Z",
          value="off", state_key="enabled",
          effective_from="2026-06-06T09:00:00Z"),
    ]
    incident_first = [
        E("ch8-f-incident2", "incident-svc", 1, "OBSERVATION_RECORDED",
          "incident-026-like", "2026-05-28T09:00:00Z", "2026-05-28T09:05:00Z",
          value="outage"),
        E("ch8-f-on2", "flag-svc", 1, "STATE_CHANGED",
          SUBJECT_FLAG, "2026-06-01T09:00:00Z", "2026-06-01T09:05:00Z",
          value="on", state_key="enabled",
          effective_from="2026-06-01T09:00:00Z"),
        E("ch8-f-off2", "flag-svc", 2, "STATE_CHANGED",
          SUBJECT_FLAG, "2026-06-06T09:00:00Z", "2026-06-06T09:05:00Z",
          value="off", state_key="enabled",
          effective_from="2026-06-06T09:00:00Z"),
    ]
    return enabled_first, incident_first


def arrival_disorder_plan() -> tuple[list[EventEnvelope], list[int]]:
    """Semantic order A->B->C with send delays producing C->A->B arrival."""
    events = canonical_migration()
    order = [e for e in events
             if e.event_id in ("ch8-benchmark", "ch8-decision", "ch8-deploy")]
    # Hand to publishers in semantic order but delay benchmark/decision so
    # deployment arrives first: arrival C, A, B.
    plan = [(order[0], 0.6), (order[1], 0.6), (order[2], 0.0)]
    return order, plan
