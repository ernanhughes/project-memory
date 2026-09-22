"""Tests for the open-loops package (Chapter 9).

Deterministic throughout; no services, no model calls. Oracle-labelled
openings isolate status maintenance from commitment extraction (Ch10).
"""

from __future__ import annotations

import pytest

from open_loops import baselines as base_mod
from open_loops import fixtures as fx
from open_loops.config import OpenLoopConfig
from open_loops.experiments import freeze, run_suite
from open_loops.health import health_report
from open_loops.materialized import MaterializedOpenList
from open_loops.metrics import score_suite
from open_loops.reverify import reverify, run_reverification
from open_loops.status import resolve_status, token_overlap

VALID = "2024-08-31T00:00:00Z"


def _canonical():
    events, texts = fx.canonical_history()
    return freeze(events), texts


# -- expectation model ------------------------------------------------

def test_oracle_openings_cover_four_futures():
    histories = fx.opening_histories()
    assert set(histories) == {"H1", "H2", "H3", "H4"}
    assert [t for _, _, t in histories.values()] == [
        "SATISFIED", "CANCELLED", "SUPERSEDED", "OPEN"]


def test_no_stored_unresolved_status():
    from open_loops.status import STATUS
    assert set(STATUS) == {"OPEN", "SATISFIED", "CANCELLED", "SUPERSEDED",
                           "UNKNOWN"}


# -- oracle status (E9-B) ----------------------------------------------

def test_matched_trajectories_resolve():
    from open_loops.experiments import exp_e9b_oracle
    assert exp_e9b_oracle()["pass"]


def test_historical_status_queries():
    log, texts = _canonical()
    exp = fx.EXP_BACKUP()
    assert resolve_status(exp, log, "2024-07-20T00:00:00Z",
                          texts=texts).status == "OPEN"
    assert resolve_status(exp, log, VALID, texts=texts).status == "SATISFIED"


def test_cancellation_not_satisfaction():
    log, texts = _canonical()
    report = resolve_status(fx.EXP_STAGING(), log, VALID, texts=texts)
    assert report.status == "CANCELLED"
    assert report.closure_tier == "explicit"


def test_supersession_not_cancellation():
    log, texts = _canonical()
    report = resolve_status(fx.EXP_TUNE(), log, VALID, texts=texts)
    assert report.status == "SUPERSEDED"


def test_superseded_and_new_obligation_not_confused():
    log, texts = _canonical()
    tune = resolve_status(fx.EXP_TUNE(), log, VALID, texts=texts)
    backup = resolve_status(fx.EXP_BACKUP(), log, VALID, texts=texts)
    assert (tune.status, backup.status) == ("SUPERSEDED", "SATISFIED")


# -- baselines ----------------------------------------------------------

def test_mention_baseline_flags_never_accepted():
    events, texts = fx.canonical_history()
    m0 = base_mod.mention_only(texts)
    assert "ch9-redis-remark" in m0  # false positive by design


def test_mention_baseline_misses_silent_completion():
    events, texts = fx.canonical_history()
    m0 = base_mod.mention_only(texts)
    # The refactor closes fixtures with no task-like text at all.
    assert "ch9-refactor" not in m0


def test_empty_and_all_open_controls():
    _, texts = fx.canonical_history()
    assert base_mod.empty_list(texts) == {}
    assert set(base_mod.all_open(texts)) >= set(base_mod.mention_only(texts))


# -- closure tiers -------------------------------------------------------

def test_cross_artifact_semantic_closure():
    from open_loops.experiments import exp_e9c_cross_artifact
    assert exp_e9c_cross_artifact()["pass"]


def test_side_effect_state_closure():
    from open_loops.experiments import exp_e9d_side_effect
    assert exp_e9d_side_effect()["pass"]


def test_false_completion_does_not_close():
    log, texts = _canonical()
    # Before the real migration, the cleanup commit must not satisfy.
    report = resolve_status(fx.EXP_BACKUP(), log, "2024-08-10T00:00:00Z",
                            texts=texts)
    assert report.status == "OPEN"


def test_token_overlap_generic():
    assert token_overlap("update deploy docs for postgresql",
                         "Update deployment docs to PostgreSQL.") >= 0.35
    assert token_overlap("backup cleanup",
                         "Move backups to PostgreSQL before release.") < 0.35


# -- duplicates ------------------------------------------------------------

def test_duplicate_mentions_are_one_obligation():
    events, texts = fx.canonical_history()
    log = freeze(events)
    report = resolve_status(fx.EXP_BACKUP(), log, VALID, texts=texts)
    assert report.status == "SATISFIED"
    assert report.closing_evidence == ("ch9-backup-migrate",)


# -- absence / footprint ------------------------------------------------------

def test_open_carries_footprint_not_bare_claim():
    log, texts = _canonical()
    trimmed = [e for e in log.events()
               if e.event_id not in ("ch9-backup-migrate", "ch9-release")]
    report = resolve_status(fx.EXP_BACKUP(), freeze(trimmed),
                            "2024-08-25T00:00:00Z", texts=texts)
    assert report.status == "OPEN"
    assert report.footprint is not None
    assert report.footprint.candidate_closures_examined >= 0
    assert "no valid closing transition" in report.detail


def test_gap_forces_unknown():
    from open_loops.experiments import exp_e9g_gap
    assert exp_e9g_gap()["pass"]


def test_bitemporal_actual_vs_believed():
    from open_loops.experiments import exp_e9h_bitemporal
    assert exp_e9h_bitemporal()["pass"]


# -- maintenance vs derivation ----------------------------------------------------

def test_maintained_matches_derived_and_rebuilds():
    from open_loops.experiments import exp_e9e_maintenance
    assert exp_e9e_maintenance()["pass"]


def test_materialized_open_list_digest_stable():
    log, texts = _canonical()
    expectations = [fx.EXP_BACKUP(), fx.EXP_DOCS(), fx.EXP_TUNE()]
    ml = MaterializedOpenList()
    for exp in expectations:
        ml.register(exp)
    for eid, text in texts.items():
        ml.note_text(eid, text)
    ml.refresh_all(log, VALID)
    first = ml.digest()
    ml.rebuild(log, VALID)
    assert ml.digest() == first
    assert {r.expectation_id for r in ml.list_open()} == set()


# -- re-verification ---------------------------------------------------------------

def test_reverification_repairs_stale_open():
    from open_loops.experiments import exp_e9i_reverify
    result = exp_e9i_reverify()
    assert result["pass"]


def test_reverify_records_provenance():
    log, texts = _canonical()
    report = reverify(fx.EXP_BACKUP(), log, VALID, texts=texts)
    assert report.last_verified_at == VALID
    assert report.status == "SATISFIED"


# -- deadline / second domain ----------------------------------------------------------

def test_deadline_flag_without_new_state():
    from open_loops.experiments import exp_deadline
    assert exp_deadline()["pass"]


def test_second_domain_event_trigger():
    from open_loops.experiments import exp_second_domain
    assert exp_second_domain()["pass"]


# -- signature demo -----------------------------------------------------------------------

def test_historian_colleague_divergence():
    from open_loops.experiments import exp_e9k_historian
    assert exp_e9k_historian()["pass"]


# -- health ---------------------------------------------------------------------------------

def test_health_report_structural():
    log, texts = _canonical()
    expectations = [fx.EXP_BACKUP(), fx.EXP_DOCS(), fx.EXP_FIXTURES(),
                    fx.EXP_TUNE(), fx.EXP_STAGING()]
    report = health_report(expectations, log)
    assert report["expectations"] == 5
    assert report["without_opening_evidence"] == []
    assert report["closing_events_without_expectation"] == []


# -- full suite -------------------------------------------------------------------------------

def test_full_suite_core_dimensions():
    suite = run_suite(OpenLoopConfig())
    metrics = score_suite(suite)
    for key in ("status_accuracy", "cross_artifact_closure_accuracy",
                "side_effect_completion_accuracy",
                "bitemporal_status_accuracy",
                "historical_status_accuracy", "history_gap_calibration",
                "search_footprint_coverage",
                "projection_rebuild_equivalence",
                "maintenance_derivation_agreement",
                "historian_colleague_demo", "deadline_flag_accuracy",
                "second_domain_accuracy", "canonical_status_accuracy",
                "reverification_repair_rate"):
        assert metrics[key] == 1.0, key
    # Mention baseline: recall without precision, by measurement.
    assert metrics["open_loop_precision"] < 1.0
    assert metrics["false_open_rate"] == 1.0
