"""Tests for the temporal-memory package (Chapter 8).

Deterministic throughout; ZeroMQ tests use in-process sockets with a
readiness gate, never sleep-based correctness.
"""

from __future__ import annotations

import pytest

from temporal_memory import fixtures as fx
from temporal_memory import model as model_mod
from temporal_memory.config import TemporalConfig
from temporal_memory.experiments import freeze, run_suite
from temporal_memory.health import health_report
from temporal_memory.log import EventLog
from temporal_memory.metrics import score_suite
from temporal_memory.ordering import admissible_role, known_before
from temporal_memory.query import (MaterializedProjection, ResolverCondition,
                                   TemporalEngine)
from temporal_memory.ordering import temporal_sort
from temporal_memory.reducer import projection_digest, replay


def _log(events=None) -> EventLog:
    return freeze(events if events is not None else fx.canonical_migration())


# -- event model ------------------------------------------------------

def test_valid_envelope_accepted():
    log = _log([])
    event = fx.canonical_migration()[0]
    log.append(event, "2026-09-20T00:00:00Z")
    assert len(log) == 1


def test_duplicate_event_id_rejected():
    log = _log([])
    event = fx.canonical_migration()[0]
    log.append(event, "2026-09-20T00:00:00Z")
    with pytest.raises(ValueError, match="DUPLICATE_EVENT_ID"):
        log.append(event, "2026-09-20T00:00:01Z")


def test_duplicate_source_seq_rejected():
    log = _log([])
    log.append(fx.canonical_migration()[0], "2026-09-20T00:00:00Z")
    dup = fx.E("ch8-other", "ledger", 1, "OBSERVATION_RECORDED",
               fx.SUBJECT_BACKEND, "2026-03-03T00:00:00Z",
               "2026-03-03T00:00:01Z")
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_SEQ"):
        log.append(dup, "2026-09-20T00:00:02Z")


def test_sequence_gap_detected():
    log = _log(fx.gap_stream())
    assert log.gaps() and log.gaps()[0]["status"] == "GAP_DETECTED"
    assert log.gaps()[0]["expected_seq"] == 18


def test_invalid_interval_rejected():
    log = _log([])
    bad = fx.E("ch8-bad", "s", 1, "STATE_CHANGED", fx.SUBJECT_BACKEND,
               "2026-01-02T00:00:00Z", "2026-01-02T00:00:01Z", value="X",
               effective_from="2026-02-01T00:00:00Z",
               effective_to="2026-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="INVALID_INTERVAL"):
        log.append(bad, "2026-09-20T00:00:00Z")


def test_unknown_parent_deferred_to_health():
    # Out-of-order arrival must remain ingestible; the missing reference
    # surfaces in health instead of rejecting the write.
    log = _log([])
    early = fx.E("ch8-early", "s", 2, "DECISION_MADE", fx.SUBJECT_BACKEND,
                 "2026-06-01T00:00:00Z", "2026-06-01T00:00:01Z",
                 causal_parents=("ch8-late",))
    log.append(early, "2026-09-20T00:00:00Z")
    assert any("UNKNOWN_CAUSAL_PARENT:ch8-late" in r
               for r in log.unknown_refs())


def test_unknown_correction_target_deferred():
    log = _log([])
    bad = fx.E("ch8-bad", "s", 1, "CORRECTION_RECORDED", fx.SUBJECT_BACKEND,
               "2026-01-02T00:00:00Z", "2026-01-02T00:00:01Z",
               corrects=("nope",))
    log.append(bad, "2026-09-20T00:00:00Z")
    assert any("UNKNOWN_CORRECTION_TARGET:nope" in r
               for r in log.unknown_refs())


def test_unknown_supersession_target_deferred():
    log = _log([])
    bad = fx.E("ch8-bad", "s", 1, "REVISION_MADE", fx.SUBJECT_BACKEND,
               "2026-01-02T00:00:00Z", "2026-01-02T00:00:01Z", value="X",
               supersedes=("nope",))
    log.append(bad, "2026-09-20T00:00:00Z")
    assert any("UNKNOWN_SUPERSEDES_TARGET:nope" in r
               for r in log.unknown_refs())


def test_future_causal_parent_flagged():
    log = _log(fx.canonical_migration())
    by_id = log.by_id()
    late = fx.E("ch8-late", "s", 1, "OBSERVATION_RECORDED",
                fx.SUBJECT_BACKEND, "2026-08-01T00:00:00Z",
                "2026-08-01T00:00:01Z")
    log.append(late, "2026-09-20T00:00:00Z")
    early = fx.E("ch8-early", "s", 2, "DECISION_MADE", fx.SUBJECT_BACKEND,
                 "2026-06-01T00:00:00Z", "2026-06-01T00:00:01Z",
                 causal_parents=("ch8-late",))
    log.append(early, "2026-09-20T00:00:01Z")
    assert any("TEMPORAL_CAUSALITY_VIOLATION" in v
               for v in log.causality_violations())


# -- reducer ----------------------------------------------------------

def test_reducer_current_and_historical():
    log = _log()
    eng = TemporalEngine(log, ResolverCondition.TEMPORAL)
    assert eng.current(fx.SUBJECT_BACKEND).value == "PostgreSQL"
    assert eng.bitemporal(
        fx.SUBJECT_BACKEND, "2026-04-01T00:00:00Z", None).value == "SQLite"


def test_decision_without_immediate_state_change():
    log = _log(fx.future_effective())
    eng = TemporalEngine(log, ResolverCondition.TEMPORAL)
    assert eng.bitemporal(
        fx.SUBJECT_BACKEND, "2026-09-10T00:00:00Z",
        "2026-09-10T00:00:00Z").value == "SQLite"
    assert eng.bitemporal(
        fx.SUBJECT_BACKEND, "2026-09-16T00:00:00Z",
        "2026-09-16T00:00:00Z").value == "PostgreSQL"


def test_revision_supersedes():
    log = _log(fx.revision_case())
    assert TemporalEngine(log, ResolverCondition.TEMPORAL).current(
        fx.SUBJECT_BACKEND).value == "PostgreSQL"


def test_correction_preserves_history():
    log = _log(fx.correction_case())
    assert "ch8-c-bench" in log.by_id()
    corr = log.by_id()["ch8-c-correction"]
    assert list(corr.corrects) == ["ch8-c-bench"]


# -- bitemporal -------------------------------------------------------

def test_late_arrival_standpoints_differ():
    log = _log(fx.late_arrival())
    eng = TemporalEngine(log, ResolverCondition.TEMPORAL)
    actual = eng.bitemporal(fx.SUBJECT_BACKEND, "2026-07-20T00:00:00Z",
                            "2026-08-10T00:00:00Z")
    believed = eng.bitemporal(fx.SUBJECT_BACKEND, "2026-07-20T00:00:00Z",
                              "2026-07-20T00:00:00Z")
    assert actual.value == "PostgreSQL"
    assert believed.value != "PostgreSQL"


# -- permutations -----------------------------------------------------

def test_sensitive_swap_changes_role():
    from temporal_memory.experiments import exp_e8b_sensitive
    assert exp_e8b_sensitive()["pass"]


def test_invariant_swap_preserves_answer():
    from temporal_memory.experiments import exp_e8c_invariant
    assert exp_e8c_invariant()["pass"]


# -- partial order ----------------------------------------------------

def test_partial_order_unknown():
    events = fx.partial_order_case()
    log = _log(events)
    by_id = log.by_id()
    assert known_before(by_id["ch8-p-a"], by_id["ch8-p-b"], by_id) is None
    assert known_before(by_id["ch8-p-a"], by_id["ch8-p-c"], by_id) is True
    assert known_before(by_id["ch8-p-b"], by_id["ch8-p-c"], by_id) is True


# -- transport --------------------------------------------------------

def test_inmemory_transport_roundtrip():
    from temporal_memory.transport import InMemoryTransport
    box: list = []
    transport = InMemoryTransport(box)
    event = fx.canonical_migration()[0]
    transport.publish(event)
    assert box and box[0]["envelope"]["event_id"] == event.event_id


def test_zeromq_multi_publisher_capture():
    zmq = pytest.importorskip("zmq")
    from temporal_memory.transport import run_live_capture
    order, plan = fx.arrival_disorder_plan()
    captured = run_live_capture([(e, 0.0) for e in order])
    got = {c["envelope"]["event_id"] for c in captured}
    assert {e.event_id for e in order} <= got


# -- materialized -----------------------------------------------------

def test_projection_matches_replay_and_rebuild():
    from temporal_memory.experiments import exp_e8j_computed_vs_materialized
    assert exp_e8j_computed_vs_materialized()["pass"]


# -- ch7 integration --------------------------------------------------

def test_temporal_admissibility_roles():
    ok, _ = admissible_role("2026-06-19T10:00:00Z", "2026-06-25T14:00:00Z",
                            "MOTIVATED_BY")
    bad, note = admissible_role("2026-06-19T10:00:00Z", "2026-06-10T14:00:00Z",
                                "MOTIVATED_BY")
    assert ok and not bad and "corroborat" in note
    ok2, _ = admissible_role("2026-06-19T10:00:00Z", "2026-06-10T14:00:00Z",
                             "CORROBORATED_BY")
    assert ok2


def test_full_suite_passes_core_dimensions():
    suite = run_suite(TemporalConfig())
    metrics = score_suite(suite)
    for key in ("temporal_role_accuracy", "order_invariant_stability",
                "late_arrival_robustness", "future_effective_accuracy",
                "correction_revision_accuracy", "partial_order_calibration",
                "sequence_gap_detection", "projection_rebuild_equivalence",
                "supersession_accuracy"):
        assert metrics[key] == 1.0, key
