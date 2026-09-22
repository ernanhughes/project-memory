"""E8 experiment suite: deterministic, ledger-scored, offline (except E8-D).

Conditions: T0 bag, T1 arrival recency, T1b event-time recency, T2
ordered reducer, T3 temporal/bitemporal. E8-D uses the live ZeroMQ
transport for capture, then freezes the log; all model comparisons
replay the frozen log. No LLM anywhere in v0.1.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from . import fixtures as fx
from .config import TemporalConfig
from .log import EventLog
from .ordering import admissible_role, known_before
from .query import MaterializedProjection, ResolverCondition, TemporalEngine
from .reducer import projection_digest, replay
from .ordering import temporal_sort

SUITE_VERSION = "e8-suite-v0.1"
SUBJECT = fx.SUBJECT_BACKEND

CONDITIONS = (
    ResolverCondition.BAG,
    ResolverCondition.ARRIVAL,
    ResolverCondition.EVENT_TIME,
    ResolverCondition.ORDERED,
    ResolverCondition.TEMPORAL,
)


def freeze(events: list[fx.EventEnvelope]) -> EventLog:
    """Ingest in arrival (given) order with recorder metadata; the frozen
    log preserves both arrival and semantic order for later replay."""
    log = EventLog()
    for i, event in enumerate(events):
        log.append(event, f"2026-09-20T00:00:{i:02d}Z")
    return log


def _current_all(log: EventLog, subject: str) -> dict[str, dict]:
    out = {}
    for cond in CONDITIONS:
        ans = TemporalEngine(log, cond).current(subject)
        out[cond] = {"value": ans.value, "status": ans.status,
                     "detail": ans.detail}
    return out


def exp_e8a_bag_vs_order() -> dict:
    """E8-A: same contents as set vs trajectory on current/historical/what-changed."""
    log = freeze(fx.canonical_migration())
    current = _current_all(log, SUBJECT)
    hist = {c: TemporalEngine(log, c).bitemporal(
        SUBJECT, "2026-04-01T00:00:00Z", None).__dict__ for c in CONDITIONS}
    hist_simple = {c: {"value": a["value"], "status": a["status"]}
                   for c, a in (("T0-bag", hist["T0-bag"]),)}
    return {
        "question": "does order add information over the event set",
        "current": current,
        "historical_april": {
            c: {"value": TemporalEngine(log, c).bitemporal(
                SUBJECT, "2026-04-01T00:00:00Z", None).value}
            for c in CONDITIONS},
        "truth": {"current": "PostgreSQL", "april": "SQLite"},
    }


def exp_e8b_sensitive() -> dict:
    """E8-B: benchmark->decision->deployment vs decision->benchmark->deployment.

    Truth: in the canonical order the benchmark is an admissible
    antecedent (MOTIVATED_BY ok); in the permuted order it is not
    (corroboration only)."""
    canon = freeze(fx.canonical_migration())
    perm = freeze(fx.permuted_decision_first())
    by_canon = canon.by_id()
    bench_c = by_canon["ch8-benchmark"]
    dec_c = by_canon["ch8-decision"]
    ok_canon, note_canon = admissible_role(bench_c.event_time,
                                           dec_c.event_time, "MOTIVATED_BY")
    by_perm = perm.by_id()
    ok_perm, note_perm = admissible_role(by_perm["ch8-benchmark"].event_time,
                                        by_perm["ch8-decision"].event_time,
                                        "MOTIVATED_BY")
    engines = {}
    for name, log in (("canonical", canon), ("permuted", perm)):
        engines[name] = {
            c: TemporalEngine(log, c).current(SUBJECT).value for c in CONDITIONS}
    return {
        "question": "does the system change its rationale exactly when order changes meaning",
        "canonical_motivated_admissible": ok_canon,
        "canonical_note": note_canon,
        "permuted_motivated_admissible": ok_perm,
        "permuted_note": note_perm,
        "expected": {"canonical": True, "permuted": False},
        "pass": ok_canon is True and ok_perm is False,
        "current_by_condition": engines,
    }


def exp_e8c_invariant() -> dict:
    """E8-C: swapping two independent events must not move the answer."""
    base, swapped = fx.invariant_pair()
    log_a, log_b = freeze(base), freeze(swapped)
    rows = {}
    for subject in (SUBJECT, "docs.readme", "frontend.css"):
        a = {c: TemporalEngine(log_a, c).current(subject).value
             for c in CONDITIONS}
        b = {c: TemporalEngine(log_b, c).current(subject).value
             for c in CONDITIONS}
        rows[subject] = {"base": a, "swapped": b,
                         "stable": {c: a[c] == b[c] for c in CONDITIONS}}
    stable_t3 = all(rows[s]["stable"][ResolverCondition.TEMPORAL]
                    for s in rows)
    return {"question": "invariance where order should not matter",
            "rows": rows, "pass": stable_t3}


def exp_e8d_arrival_disorder(use_live_transport: bool = False) -> dict:
    """E8-D: semantic A->B->C arrives C->A->B. Arrival-order resolution
    must fail; the temporal resolver must recover."""
    order, plan = fx.arrival_disorder_plan()
    arrivals: list[str]
    if use_live_transport:
        from .transport import run_live_capture
        captured = run_live_capture(plan)
        arrivals = [c["envelope"]["event_id"] for c in captured]
        log = EventLog()
        for rec in captured:
            from .model import EventEnvelope as EE
            log.append(EE.from_dict(rec["envelope"]), rec["received_at"])
    else:
        # Deterministic emulation of the same disorder: ingest C, A, B.
        ingest = [order[2], order[0], order[1]]
        arrivals = [e.event_id for e in ingest]
        log = freeze(ingest)
    semantic = [e.event_id for e in order]
    resolved = log.event_time_order()
    t1 = TemporalEngine(log, ResolverCondition.ARRIVAL).current(SUBJECT)
    t3 = TemporalEngine(log, ResolverCondition.TEMPORAL).current(SUBJECT)
    return {
        "question": "transport order is an observation; temporal order is the model",
        "semantic_order": semantic,
        "arrival_order": arrivals,
        "resolved_temporal_order": resolved,
        "arrival_resolver": {"value": t1.value, "status": t1.status},
        "temporal_resolver": {"value": t3.value, "status": t3.status,
                              "detail": t3.detail},
        "transport_mode": "live-zeromq" if use_live_transport else "emulated-disorder",
    }


def exp_e8e_late_arrival() -> dict:
    """E8-E: July 10 cutover learned August 3. Matched standpoint pair."""
    log = freeze(fx.late_arrival())
    eng = TemporalEngine(log, ResolverCondition.TEMPORAL)
    q_true = eng.bitemporal(SUBJECT, "2026-07-20T00:00:00Z", "2026-08-10T00:00:00Z")
    q_knew = eng.bitemporal(SUBJECT, "2026-07-20T00:00:00Z", "2026-07-20T00:00:00Z")
    return {
        "question": "what was true vs what was known",
        "true_july20_known_aug10": {"value": q_true.value,
                                    "detail": q_true.detail},
        "known_july20": {"value": q_knew.value, "detail": q_knew.detail},
        "truth": {"actual": "PostgreSQL", "believed_at_time": "SQLite"},
        "pass": q_true.value == "PostgreSQL" and q_knew.value != "PostgreSQL",
    }


def exp_e8f_future_effective() -> dict:
    """E8-F: Sept 1 decision effective Sept 15. Current vs planned differ."""
    log = freeze(fx.future_effective())
    eng = TemporalEngine(log, ResolverCondition.TEMPORAL)
    before = eng.bitemporal(SUBJECT, "2026-09-10T00:00:00Z", "2026-09-10T00:00:00Z")
    after = eng.bitemporal(SUBJECT, "2026-09-16T00:00:00Z", "2026-09-16T00:00:00Z")
    cur = eng.current(SUBJECT)
    return {
        "question": "a decision can exist before it takes effect",
        "sept10": {"value": before.value, "detail": before.detail},
        "sept16": {"value": after.value, "detail": after.detail},
        "current": {"value": cur.value},
        "truth": {"sept10": "SQLite", "sept16": "PostgreSQL"},
        "pass": before.value == "SQLite" and after.value == "PostgreSQL",
    }


def exp_e8g_correction() -> dict:
    """E8-G: correction appends; historical decision context preserved."""
    log = freeze(fx.correction_case())
    eng = TemporalEngine(log, ResolverCondition.TEMPORAL)
    believed_then = eng.bitemporal("event-store.backend", "2026-06-25T15:00:00Z",
                                   "2026-06-25T15:00:00Z")
    speedup_now = eng.current("event-store.backend")
    # Speedup subject carries the corrected value.
    log2_events = [e for e in log.events()]
    bench_then = [e.value for e in log2_events if e.event_id == "ch8-c-bench"][0]
    corr = [e for e in log2_events if e.event_id == "ch8-c-correction"][0]
    history_ids = [h["event"] for h in eng.history("event-store.backend")]
    return {
        "question": "correcting history without deleting it",
        "benchmark_recorded": bench_then,
        "correction_value": corr.value,
        "correction_target": list(corr.corrects),
        "earlier_record_preserved": "ch8-c-bench" in log.by_id(),
        "log_is_append_only": len(log) == 4,
        "pass": ("ch8-c-bench" in log.by_id()
                 and list(corr.corrects) == ["ch8-c-bench"]),
        "decision_context": {"value": believed_then.value},
    }


def exp_e8h_partial_order() -> dict:
    """E8-H: A,B both before C; A/B order unknown. No invented total order."""
    events = fx.partial_order_case()
    log = freeze(events)
    by_id = log.by_id()
    a, b, c = by_id["ch8-p-a"], by_id["ch8-p-b"], by_id["ch8-p-c"]
    rel_ab = known_before(a, b, by_id)
    rel_ac = known_before(a, c, by_id)
    rel_bc = known_before(b, c, by_id)
    return {
        "question": "concurrent events keep unknown order",
        "a_before_b": rel_ab,
        "a_before_c": rel_ac,
        "b_before_c": rel_bc,
        "pass": rel_ab is None and rel_ac is True and rel_bc is True,
    }


def exp_e8i_gap() -> dict:
    """E8-I: seq 17 then 19 -> GAP_DETECTED + INCOMPLETE_HISTORY, no
    confident reconstruction."""
    log = freeze(fx.gap_stream())
    eng = TemporalEngine(log, ResolverCondition.TEMPORAL)
    ans = eng.current(SUBJECT)
    return {
        "question": "missing events must surface uncertainty",
        "gaps": log.gaps(),
        "answer": {"value": ans.value, "status": ans.status,
                   "detail": ans.detail},
        "pass": bool(log.gaps()) and "INCOMPLETE_HISTORY" in ans.detail,
    }


def exp_e8j_computed_vs_materialized(scale: int = 0) -> dict:
    """E8-J: maintained projection vs query-time replay; rebuild equivalence."""
    import time as _t
    events = fx.canonical_migration()
    if scale > 0:
        events = list(events)
        for i in range(scale):
            events.append(fx.E(
                f"ch8-scale-{i}", "scale-svc", i + 1, "OBSERVATION_RECORDED",
                SUBJECT, "2026-06-01T00:00:00Z", "2026-06-01T00:00:01Z"))
    log = freeze(events)
    by_id = log.by_id()
    ordered = temporal_sort(log.events(), by_id)
    t0 = _t.perf_counter()
    computed = replay(ordered)
    replay_ms = (_t.perf_counter() - t0) * 1000
    mat = MaterializedProjection()
    t0 = _t.perf_counter()
    for e in log.events():  # ingest in arrival order
        mat.ingest(e, "2026-09-20T00:00:00Z")
    ingest_ms = (_t.perf_counter() - t0) * 1000
    digest_computed = projection_digest(computed)
    digest_mat = projection_digest(mat.projection)
    # Correction propagation: append correction, compare again.
    corr = fx.E("ch8-j-corr", "benchmark-svc", 99, "CORRECTION_RECORDED",
                SUBJECT, "2026-07-05T10:00:00Z", "2026-07-05T10:05:00Z",
                corrects=("ch8-benchmark",))
    log.append(corr, "2026-09-20T00:00:10Z")
    ordered2 = temporal_sort(log.events(), log.by_id())
    computed2 = replay(ordered2)
    mat.ingest(corr, "2026-09-20T00:00:10Z")
    digest_c2 = projection_digest(computed2)
    digest_m2 = projection_digest(mat.projection)
    # Rebuild equivalence.
    rebuilt = MaterializedProjection()
    rebuilt.rebuild(ordered2)
    digest_rebuilt = projection_digest(rebuilt.projection)
    t0 = _t.perf_counter()
    TemporalEngine(log, ResolverCondition.TEMPORAL).current(SUBJECT)
    query_ms = (_t.perf_counter() - t0) * 1000
    return {
        "question": "computed vs materialized belief",
        "replay_ms": round(replay_ms, 2),
        "ingest_ms": round(ingest_ms, 2),
        "query_ms": round(query_ms, 2),
        "projection_equivalent": digest_computed == digest_mat,
        "correction_equivalent": digest_c2 == digest_m2,
        "rebuild_equivalent": digest_rebuilt == digest_m2,
        "storage_events": len(log),
        "pass": (digest_computed == digest_mat and digest_c2 == digest_m2
                 and digest_rebuilt == digest_m2),
    }


def exp_second_domain() -> dict:
    """Second-domain permutation: flag/incident order changes admissibility."""
    on_first, inc_first = fx.second_domain()
    la, lb = freeze(on_first), freeze(list(inc_first))
    return {
        "question": "mechanism generalises beyond the database migration",
        "flag_first_current": TemporalEngine(
            la, ResolverCondition.TEMPORAL).current(fx.SUBJECT_FLAG).value,
        "incident_first_current": TemporalEngine(
            lb, ResolverCondition.TEMPORAL).current(fx.SUBJECT_FLAG).value,
        "note": "precedence rules out contribution claims; it never proves them",
    }


def run_suite(config: TemporalConfig | None = None,
              live_transport: bool = False) -> dict:
    """Run E8-A..E8-J and freeze the manifest."""
    config = config or TemporalConfig()
    started = time.perf_counter()
    experiments = {
        "E8-A": exp_e8a_bag_vs_order(),
        "E8-B": exp_e8b_sensitive(),
        "E8-C": exp_e8c_invariant(),
        "E8-D": exp_e8d_arrival_disorder(use_live_transport=live_transport),
        "E8-E": exp_e8e_late_arrival(),
        "E8-F": exp_e8f_future_effective(),
        "E8-G": exp_e8g_correction(),
        "E8-H": exp_e8h_partial_order(),
        "E8-I": exp_e8i_gap(),
        "E8-J": exp_e8j_computed_vs_materialized(),
        "E8-second-domain": exp_second_domain(),
    }
    elapsed_ms = (time.perf_counter() - started) * 1000
    for name, experiment in experiments.items():
        experiment["question_id"] = name
    log = freeze(fx.canonical_migration())
    return {
        "suite": SUITE_VERSION,
        "config": config.to_dict(),
        "frozen_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "model_dependency": "none (ledger-deterministic-v0.1)",
        "experiments": experiments,
        "costs": {"llm_calls": 0, "tokens": 0,
                  "latency_ms": round(elapsed_ms, 1)},
        "log_digest": log.digest(),
    }
