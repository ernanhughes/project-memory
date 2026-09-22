"""Chapter 2 Measurement Instrument adapter: Q5 metrics over E9 runs."""

from __future__ import annotations

from . import fixtures as fx
from .experiments import freeze
from .status import resolve_status


def score_suite(suite: dict) -> dict:
    """Score the frozen E9 suite into instrument-style metrics (each
    dimension reported separately; no single aggregate score)."""
    ex = suite["experiments"]
    metrics: dict[str, float] = {}

    # Status accuracy over the oracle H1-H4 family (E9-B).
    rows = ex["E9-B"]["rows"]
    metrics["status_accuracy"] = sum(
        1.0 for r in rows.values() if r["pass"]) / len(rows)

    # Cross-artifact closure (E9-C) and side-effect completion (E9-D).
    metrics["cross_artifact_closure_accuracy"] = 1.0 if ex["E9-C"]["pass"] else 0.0
    metrics["side_effect_completion_accuracy"] = 1.0 if ex["E9-D"]["pass"] else 0.0

    # Mention baseline precision/recall at the expectation level (E9-A/K).
    # Genuine obligations: the five canonical expectations expressible as
    # mentions; M0 flags 5 texts, 1 a false positive (Redis remark).
    m0_fp = len(ex["E9-A"]["M0_false_positives"])
    m0_n = len(ex["E9-A"]["M0_open"])
    metrics["open_loop_precision"] = ((m0_n - m0_fp) / m0_n) if m0_n else 1.0
    metrics["open_loop_recall"] = ex["E9-A"]["M0_recall_genuine"]
    metrics["false_open_rate"] = 1.0 if ex["E9-A"]["redis_remark_flagged_M0"] else 0.0
    # M3 on the canonical history: no false closes (all six match truth).
    events, texts = fx.canonical_history()
    log = freeze(events)
    expectations = [fx.EXP_BACKUP(), fx.EXP_DOCS(), fx.EXP_FIXTURES(),
                    fx.EXP_TUNE(), fx.EXP_STAGING()]
    got = {e.expectation_id: resolve_status(
        e, log, "2024-08-31T00:00:00Z", texts=texts).status
        for e in expectations}
    want = {k: v for k, v in fx.CANONICAL_TRUTH.items() if k != "exp-docs-sem"}
    metrics["canonical_status_accuracy"] = sum(
        1.0 for k, v in want.items() if got.get(k) == v) / len(want)
    metrics["false_closed_rate"] = sum(
        1.0 for k, v in want.items()
        if got.get(k) != "OPEN" and v == "OPEN") / len(want)

    # Stale-open dynamics (E9-I): 1.0 iff re-verification repairs fully.
    metrics["stale_open_rate"] = ex["E9-I"]["stale_open_cycles_without_reverify"] / 3.0
    metrics["reverification_repair_rate"] = (
        1.0 if ex["E9-I"]["stale_open_cycles_with_reverify"] == 0 else 0.0)

    # Temporal/bitemporal status (E9-H), gap calibration (E9-G).
    metrics["bitemporal_status_accuracy"] = 1.0 if ex["E9-H"]["pass"] else 0.0
    metrics["historical_status_accuracy"] = 1.0 if ex["E9-B"]["pass"] else 0.0
    metrics["history_gap_calibration"] = 1.0 if ex["E9-G"]["pass"] else 0.0

    # Footprint auditability (E9-F), maintenance equivalence (E9-E),
    # signature demo (E9-K), deadline flags, second domain.
    metrics["search_footprint_coverage"] = 1.0 if ex["E9-F"]["pass"] else 0.0
    metrics["projection_rebuild_equivalence"] = (
        1.0 if ex["E9-E"]["rebuild_digest_match"] else 0.0)
    metrics["maintenance_derivation_agreement"] = (
        1.0 if ex["E9-E"]["agree"] else 0.0)
    metrics["historian_colleague_demo"] = 1.0 if ex["E9-K"]["pass"] else 0.0
    metrics["deadline_flag_accuracy"] = 1.0 if ex["E9-deadline"]["pass"] else 0.0
    metrics["second_domain_accuracy"] = (
        1.0 if ex["E9-second-domain"]["pass"] else 0.0)
    return metrics
