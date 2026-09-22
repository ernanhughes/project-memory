"""E9 experiment suite: deterministic, ledger-scored, offline.

Conditions mirror the benchmark ladder's discipline applied to time:
- M0 mention-only, M1 mention+nearby-closure (text baselines);
- M2 full-history derivation (query-time, no stored state);
- M3 maintained status (MaterializedOpenList);
- M4 maintained + world-state corroboration (secondary);
- empty-list / all-open sanity controls; oracle-opening throughout.

No LLM anywhere in v0.1. Fixture truth is the ledger; metrics follow
spec Q5 (open-loop precision/recall, completion-status accuracy,
stale-task rate), conditioned on history presence.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from temporal_memory.ordering import temporal_sort

from . import baselines as base_mod
from . import fixtures as fx
from .config import OpenLoopConfig
from .fixtures import freeze
from .materialized import MaterializedOpenList
from .model import Expectation
from .reverify import run_reverification
from .status import resolve_status

SUITE_VERSION = "e9-suite-v0.1"


def _m3(log, expectations, texts, valid_at, config):
    ml = MaterializedOpenList(config)
    for exp in expectations:
        ml.register(exp)
    for eid, text in texts.items():
        ml.note_text(eid, text)
    ml.refresh_all(log, valid_at)
    return ml


def exp_e9a_mention() -> dict:
    """E9-A: M0/M1 over canonical texts vs ledger truth."""
    events, texts = fx.canonical_history()
    # Mention-level scoring: which task-like mentions are genuine.
    m0 = base_mod.mention_only(texts)
    m1 = base_mod.mention_nearby_closure(texts)
    genuine = {"ch9-backup-todo", "ch9-backup-checklist", "ch9-tune-task",
               "ch9-docs-open"}
    m0_ids, m1_ids = set(m0), set(m1)
    fp_m0 = sorted(m0_ids - genuine - {"ch9-backup-remark"})
    # ch9-backup-remark is a genuine opening mention, not a false positive.
    m0_hits = m0_ids & (genuine | {"ch9-backup-remark"})
    return {
        "question": "mention recall without precision",
        "M0_open": sorted(m0_ids),
        "M1_open": sorted(m1_ids),
        "M0_false_positives": sorted(m0_ids - genuine - {"ch9-backup-remark"}),
        "M1_false_positives": sorted(m1_ids - genuine - {"ch9-backup-remark"}),
        "redis_remark_flagged_M0": "ch9-redis-remark" in m0,
        "redis_remark_flagged_M1": "ch9-redis-remark" in m1,
        "M0_recall_genuine": len(m0_hits) / len(genuine | {"ch9-backup-remark"}),
    }


def exp_e9b_oracle() -> dict:
    """E9-B: oracle openings + status resolution over H1-H4."""
    histories = fx.opening_histories()
    exp_h = fx.EXP_H()
    rows = {}
    for name, (events, texts, truth) in histories.items():
        log = freeze(events)
        report = resolve_status(exp_h, log, "2024-08-31T00:00:00Z",
                                texts=texts)
        rows[name] = {"got": report.status, "want": truth,
                      "tier": report.closure_tier,
                      "detail": report.closing_evidence,
                      "pass": report.status == truth}
    return {"question": "same opening, four trajectories, four statuses",
            "rows": rows,
            "pass": all(r["pass"] for r in rows.values())}


def exp_e9c_cross_artifact() -> dict:
    """E9-C: session opens, commit/diff/state closes; tiers separated."""
    events = [
        fx.E("ch9-c-open", "session-051", 1, "OBSERVATION_RECORDED",
             fx.SUBJECT_DOCS, "2024-07-22T10:00:00Z", "2024-07-22T10:05:00Z"),
        fx.E("ch9-c-sem", "commit-117", 1, "OBSERVATION_RECORDED",
             fx.SUBJECT_DOCS, "2024-08-20T10:00:00Z", "2024-08-20T10:05:00Z"),
    ]
    texts = {"ch9-c-open": "Deployment documentation still describes SQLite; need docs update.",
             "ch9-c-sem": "update deploy docs for postgresql"}
    exp = fx.EXP_DOCS_SEM()
    log = freeze(events)
    report = resolve_status(exp, log, "2024-08-31T00:00:00Z", texts=texts)
    m0 = base_mod.mention_only(texts)
    return {
        "question": "promise linked to fulfilment across artifact types",
        "status": report.status,
        "tier": report.closure_tier,
        "mention_baseline_lists_opening": bool(m0),
        "pass": report.status == "SATISFIED"
                and report.closure_tier == "semantic",
    }


def exp_e9d_side_effect() -> dict:
    """E9-D: fulfilment with no textual link (refactor updates fixtures)."""
    events = [
        fx.E("ch9-d-open", "docs-note", 1, "OBSERVATION_RECORDED",
             fx.SUBJECT_FIXTURES, "2024-07-22T10:00:00Z",
             "2024-07-22T10:05:00Z"),
        fx.E("ch9-d-refactor", "commit-120", 1, "STATE_CHANGED",
             fx.SUBJECT_FIXTURES, "2024-08-12T10:00:00Z",
             "2024-08-12T10:05:00Z", value="PostgreSQL",
             effective_from="2024-08-12T10:00:00Z"),
    ]
    texts = {"ch9-d-open": "Benchmark fixtures assume SQLite timings; update them.",
             "ch9-d-refactor": "speed up importer test harness"}
    exp = fx.EXP_FIXTURES()
    log = freeze(events)
    report = resolve_status(exp, log, "2024-08-31T00:00:00Z", texts=texts)
    m0 = base_mod.mention_only(texts)
    return {
        "question": "outcomes tracked, not keywords",
        "status": report.status,
        "tier": report.closure_tier,
        "mention_baseline_sees_anything": bool(m0),
        "pass": report.status == "SATISFIED"
                and report.closure_tier == "state-transition",
    }


def exp_e9e_maintenance() -> dict:
    """E9-E: M2 derived vs M3 maintained — quality, latency, staleness."""
    import time as _t
    events, texts = fx.canonical_history()
    log = freeze(events)
    expectations = [fx.EXP_BACKUP(), fx.EXP_DOCS(), fx.EXP_FIXTURES(),
                    fx.EXP_TUNE(), fx.EXP_STAGING()]
    config = OpenLoopConfig()
    valid = "2024-08-31T00:00:00Z"
    t0 = _t.perf_counter()
    derived = {e.expectation_id: resolve_status(e, log, valid, config=config,
                                                texts=texts).status
               for e in expectations}
    derived_ms = (_t.perf_counter() - t0) * 1000
    ml = _m3(log, expectations, texts, valid, config)
    t0 = _t.perf_counter()
    listed = {r.expectation_id for r in ml.list_open()}
    list_ms = (_t.perf_counter() - t0) * 1000
    maintained = {e.expectation_id: ml.statuses[e.expectation_id].status
                  for e in expectations}
    # Staleness probe: freeze the maintained list at 08-25 knowledge, then
    # let the 08-27 closure land. M2 (derived at 08-31) sees it; M3 does
    # not until refreshed — the staleness risk of maintenance, measured.
    ml_stale = MaterializedOpenList(config)
    for exp in expectations:
        ml_stale.register(exp)
    for eid, text in texts.items():
        ml_stale.note_text(eid, text)
    ml_stale.refresh_all(log, "2024-08-25T00:00:00Z")
    stale = ml_stale.statuses["intent-401"].status
    ml_stale.refresh_all(log, "2024-09-05T00:00:00Z")
    repaired = ml_stale.statuses["intent-401"].status
    ml2 = MaterializedOpenList(config)
    for exp in expectations:
        ml2.register(exp)
    for eid, text in texts.items():
        ml2.note_text(eid, text)
    ml2.rebuild(log, valid)
    return {
        "question": "maintained status vs on-demand derivation",
        "derived": derived,
        "maintained": maintained,
        "agree": derived == maintained,
        "derived_query_ms": round(derived_ms, 2),
        "materialized_list_ms": round(list_ms, 2),
        "stale_without_refresh": stale,
        "after_refresh": repaired,
        "rebuild_digest_match": ml.digest() == ml2.digest(),
        "pass": derived == maintained and ml.digest() == ml2.digest(),
    }


def exp_e9f_footprint() -> dict:
    """E9-F: status with vs without footprint; auditability, not accuracy."""
    events, texts = fx.canonical_history()
    # H4-style: opening with no closure anywhere.
    log = freeze([e for e in events
                  if e.event_id not in ("ch9-backup-migrate", "ch9-release")])
    exp = fx.EXP_BACKUP()
    report = resolve_status(exp, log, "2024-08-25T00:00:00Z", texts=texts)
    without = {"status": report.status}
    with_fp = {"status": report.status,
               "footprint": report.footprint.to_dict(),
               "confidence": report.confidence_class}
    return {
        "question": "does the footprint change auditability",
        "status_identical": without["status"] == with_fp["status"],
        "footprint_channels": with_fp["footprint"]["searched_sources"],
        "confidence": with_fp["confidence"],
        "pass": without["status"] == "OPEN" == with_fp["status"]
                and bool(with_fp["footprint"]["searched_sources"]),
    }


def exp_e9g_gap() -> dict:
    """E9-G: omitted possible closing event -> UNKNOWN, not confident open."""
    events = [
        fx.E("ch9-g-open", "session-051", 1, "OBSERVATION_RECORDED",
             fx.SUBJECT_BACKUP, "2024-07-17T10:00:00Z",
             "2024-07-17T10:05:00Z"),
        fx.E("ch9-g-5", "commit-118", 5, "OBSERVATION_RECORDED",
             fx.SUBJECT_BACKUP, "2024-08-20T10:00:00Z",
             "2024-08-20T10:05:00Z"),
        fx.E("ch9-g-7", "commit-118", 7, "OBSERVATION_RECORDED",
             fx.SUBJECT_BACKUP, "2024-08-28T10:00:00Z",
             "2024-08-28T10:05:00Z"),
    ]
    texts = {"ch9-g-open": "Backups still target SQLite - need to move those before release.",
             "ch9-g-5": "backup scripts touched",
             "ch9-g-7": "backup scripts touched again"}
    exp = fx.EXP_BACKUP()
    log = freeze(events)
    report = resolve_status(exp, log, "2024-08-31T00:00:00Z", texts=texts)
    return {
        "question": "absence calibrated by history completeness",
        "status": report.status,
        "gaps": log.gaps(),
        "pass": report.status in ("UNKNOWN", "OPEN")
                and "INCOMPLETE" in (report.confidence_class
                                     + report.detail),
    }


def exp_e9h_bitemporal() -> dict:
    """E9-H: completion recorded late; actual vs believed status differ."""
    events = [
        fx.E("ch9-h-open", "session-051", 1, "OBSERVATION_RECORDED",
             fx.SUBJECT_BACKUP, "2024-07-17T10:00:00Z",
             "2024-07-17T10:05:00Z"),
        fx.E("ch9-h-close", "commit-118", 1, "STATE_CHANGED",
             fx.SUBJECT_BACKUP, "2024-08-27T10:00:00Z",
             "2024-09-05T10:05:00Z", value="PostgreSQL",
             effective_from="2024-08-27T10:00:00Z",
             evidence_refs=("commit-118",)),
    ]
    texts = {"ch9-h-open": "Backups still target SQLite - need to move those before release.",
             "ch9-h-close": "prepare release storage changes"}
    exp = fx.EXP_BACKUP()
    log = freeze(events)
    actual = resolve_status(exp, log, "2024-08-28T00:00:00Z",
                            "2024-09-10T00:00:00Z", texts=texts)
    believed = resolve_status(exp, log, "2024-08-28T00:00:00Z",
                              "2024-08-28T00:00:00Z", texts=texts)
    return {
        "question": "what was open vs what was believed open",
        "actual_aug28": actual.status,
        "believed_aug28": believed.status,
        "pass": actual.status == "SATISFIED" and believed.status == "OPEN",
    }


def exp_e9i_reverify() -> dict:
    """E9-I: long simulation; stale-open rate with vs without reverify."""
    config = OpenLoopConfig()
    cycles = 8
    # Each cycle adds unrelated history; delayed closure lands at cycle 5.
    base = [
        fx.E("ch9-i-open", "session-051", 1, "OBSERVATION_RECORDED",
             fx.SUBJECT_BACKUP, "2024-07-17T10:00:00Z",
             "2024-07-17T10:05:00Z"),
    ]
    exp = fx.EXP_BACKUP()
    texts = {"ch9-i-open": "Backups still target SQLite - need to move those before release."}
    late_close = fx.E("ch9-i-close", "commit-118", 1, "STATE_CHANGED",
                      fx.SUBJECT_BACKUP, "2024-08-27T10:00:00Z",
                      "2024-08-27T10:05:00Z", value="PostgreSQL",
                      effective_from="2024-08-27T10:00:00Z")
    stale_opens_no, stale_opens_yes = 0, 0
    ml_frozen = MaterializedOpenList(config)
    ml_kept = MaterializedOpenList(config)
    for ml in (ml_frozen, ml_kept):
        ml.register(exp)
        ml.note_text("ch9-i-open", texts["ch9-i-open"])
    events = list(base)
    for cycle in range(cycles):
        events.append(fx.E(f"ch9-i-noise-{cycle}", "commit-119", cycle + 1,
                           "OBSERVATION_RECORDED", "frontend.css",
                           f"2024-08-{10 + cycle:02d}T10:00:00Z",
                           f"2024-08-{10 + cycle:02d}T10:05:00Z"))
        if cycle == 5:
            # Delayed closure evidence arrives in history...
            events.append(late_close)
            for ml in (ml_frozen, ml_kept):
                ml.note_text("ch9-i-close", "prepare release storage changes")
        log = freeze(events)
        # ...but the frozen list keeps cycle-0 knowledge forever.
        if cycle == 0:
            for ml in (ml_frozen, ml_kept):
                ml.refresh_all(log, "2024-08-10T00:00:00Z")
        snapshot = resolve_status(exp, log, "2024-08-31T00:00:00Z",
                                  config=config, texts=dict(texts, **ml_kept.texts))
        if cycle >= 5:
            if ml_frozen.statuses["intent-401"].status == "OPEN" \
                    and snapshot.status == "SATISFIED":
                stale_opens_no += 1
            if cycle % config.reverify_every_cycles == 0 or cycle == 5:
                run_reverification(ml_kept, log, "2024-08-31T00:00:00Z")
            if ml_kept.statuses["intent-401"].status == "OPEN" \
                    and snapshot.status == "SATISFIED":
                stale_opens_yes += 1
    return {
        "question": "do open lists accumulate mistakes without rechecking",
        "stale_open_cycles_without_reverify": stale_opens_no,
        "stale_open_cycles_with_reverify": stale_opens_yes,
        "pass": stale_opens_no >= 3 and stale_opens_yes == 0,
    }


def exp_e9j_snapshot() -> dict:
    """E9-J (secondary): history-only vs history + current-state snapshot."""
    events = [
        fx.E("ch9-j-open", "session-051", 1, "OBSERVATION_RECORDED",
             fx.SUBJECT_BACKUP, "2024-07-17T10:00:00Z",
             "2024-07-17T10:05:00Z"),
    ]
    texts = {"ch9-j-open": "Backups still target SQLite - need to move those before release."}
    exp = fx.EXP_BACKUP()
    log = freeze(events)
    history_only = resolve_status(exp, log, "2024-08-25T00:00:00Z",
                                  texts=texts,
                                  current_state_checked=False)
    corroborated = resolve_status(exp, log, "2024-08-25T00:00:00Z",
                                  texts=texts,
                                  current_state_checked=True)
    return {
        "question": "does a snapshot change anything beyond confidence",
        "history_only": (history_only.status, history_only.confidence_class),
        "corroborated": (corroborated.status,
                         corroborated.footprint.current_state_checked),
        "pass": history_only.status == "OPEN"
                and corroborated.status == "OPEN"
                and corroborated.footprint is not None
                and corroborated.footprint.current_state_checked,
    }


def exp_e9k_historian() -> dict:
    """E9-K: perfect historian, bad colleague — Q1-Q4 pass, M0 Q5 fails."""
    events, texts = fx.canonical_history()
    log = freeze(events)
    # Historian checks: opening present, closing present, Ch8 belief right.
    from temporal_memory.query import ResolverCondition, TemporalEngine
    opening_present = "ch9-backup-remark" in log.by_id()
    closing_present = "ch9-backup-migrate" in log.by_id()
    belief = TemporalEngine(log, ResolverCondition.TEMPORAL).current(
        fx.SUBJECT_BACKUP).value
    m0 = base_mod.mention_only(texts)
    # M0 reports the backup TODO open forever: stale-open after Aug 27.
    m0_says_open = "ch9-backup-todo" in m0 and m0["ch9-backup-todo"] == "OPEN"
    m3 = resolve_status(fx.EXP_BACKUP(), log, "2024-08-31T00:00:00Z",
                        texts=texts)
    return {
        "question": "history perfect, assistance failed",
        "opening_present": opening_present,
        "closing_present": closing_present,
        "ch8_current_belief": belief,
        "historian_passes": opening_present and closing_present
                             and belief == "PostgreSQL",
        "M0_reports_stale_open": m0_says_open,
        "M3_status": m3.status,
        "pass": opening_present and closing_present
                and belief == "PostgreSQL"
                and m0_says_open and m3.status == "SATISFIED",
    }


def exp_deadline() -> dict:
    """Deadline obligation: release without satisfaction -> OPEN + flag."""
    events = [
        fx.E("ch9-t-open", "ch9-token-open", 1, "OBSERVATION_RECORDED",
             fx.SUBJECT_TOKEN, "2024-09-01T10:00:00Z",
             "2024-09-01T10:05:00Z"),
        fx.E("ch9-t-bound", "release-svc", 1, "OBSERVATION_RECORDED",
             "calendar", "2024-09-30T10:00:00Z", "2024-09-30T10:05:00Z"),
    ]
    texts = {"ch9-t-open": "Rotate the service token before 30 September."}
    exp = fx.EXP_TOKEN()
    log = freeze(events)
    before = resolve_status(exp, log, "2024-09-15T00:00:00Z", texts=texts)
    after = resolve_status(exp, log, "2024-10-05T00:00:00Z", texts=texts)
    return {
        "question": "bounded obligation finitely decidable",
        "before_deadline": (before.status, before.deadline_passed),
        "after_deadline": (after.status, after.deadline_passed),
        "pass": before.status == "OPEN" and not before.deadline_passed
                and after.status == "OPEN" and after.deadline_passed,
    }


def exp_second_domain() -> dict:
    """Event-triggered obligation beyond backups: disable flag post-incident."""
    events = [
        fx.E("ch9-incident", "incident-svc", 1, "OBSERVATION_RECORDED",
             "incident-026-like", "2024-08-01T10:00:00Z",
             "2024-08-01T10:05:00Z", value="outage"),
        fx.E("ch9-flag-off", "flag-svc", 1, "STATE_CHANGED",
             fx.SUBJECT_FLAG, "2024-08-05T10:00:00Z",
             "2024-08-05T10:05:00Z", value="off",
             effective_from="2024-08-05T10:00:00Z"),
    ]
    exp = fx.EXP_FLAG()
    log = freeze(events)
    report = resolve_status(exp, log, "2024-08-31T00:00:00Z")
    return {"question": "mechanism generalises beyond migrations",
            "status": report.status, "tier": report.closure_tier,
            "pass": report.status == "SATISFIED"}


def run_suite(config: OpenLoopConfig | None = None) -> dict:
    """Run E9-A..E9-K and freeze the manifest."""
    config = config or OpenLoopConfig()
    started = time.perf_counter()
    experiments = {
        "E9-A": exp_e9a_mention(),
        "E9-B": exp_e9b_oracle(),
        "E9-C": exp_e9c_cross_artifact(),
        "E9-D": exp_e9d_side_effect(),
        "E9-E": exp_e9e_maintenance(),
        "E9-F": exp_e9f_footprint(),
        "E9-G": exp_e9g_gap(),
        "E9-H": exp_e9h_bitemporal(),
        "E9-I": exp_e9i_reverify(),
        "E9-J": exp_e9j_snapshot(),
        "E9-K": exp_e9k_historian(),
        "E9-deadline": exp_deadline(),
        "E9-second-domain": exp_second_domain(),
    }
    elapsed_ms = (time.perf_counter() - started) * 1000
    for name, experiment in experiments.items():
        experiment["question_id"] = name
    events, _ = fx.canonical_history()
    log = freeze(events)
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
