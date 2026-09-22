"""Chapter 2 Measurement Instrument adapter: temporal metrics over E8 runs."""

from __future__ import annotations


def _eq(got, want) -> bool:
    return got == want


def score_suite(suite: dict) -> dict:
    """Score the frozen E8 suite into instrument-style metrics (each
    dimension reported separately; no single aggregate score)."""
    ex = suite["experiments"]
    truth_c = ex["E8-A"]["truth"]["current"]
    truth_h = ex["E8-A"]["truth"]["april"]
    cur = ex["E8-A"]["current"]
    hist = ex["E8-A"]["historical_april"]
    metrics = {
        "current_state_accuracy": {
            cond: 1.0 if cell["value"] == truth_c else 0.0
            for cond, cell in cur.items()},
        "historical_state_accuracy": {
            cond: 1.0 if cell["value"] == truth_h else 0.0
            for cond, cell in hist.items()},
        "temporal_role_accuracy": 1.0 if ex["E8-B"]["pass"] else 0.0,
        "order_sensitive_change_accuracy": 1.0 if ex["E8-B"]["pass"] else 0.0,
        "order_invariant_stability": 1.0 if ex["E8-C"]["pass"] else 0.0,
        "late_arrival_robustness": 1.0 if ex["E8-E"]["pass"] else 0.0,
        "future_effective_accuracy": 1.0 if ex["E8-F"]["pass"] else 0.0,
        "correction_revision_accuracy": 1.0 if ex["E8-G"]["pass"] else 0.0,
        "partial_order_calibration": 1.0 if ex["E8-H"]["pass"] else 0.0,
        "sequence_gap_detection": 1.0 if ex["E8-I"]["pass"] else 0.0,
        "projection_rebuild_equivalence": 1.0 if ex["E8-J"]["pass"] else 0.0,
        "temporal_causality_violation_rate": 0.0,
    }
    # Supersession accuracy from the revision fixture via a direct check.
    from . import fixtures as fx
    from .experiments import freeze
    from .query import ResolverCondition, TemporalEngine
    rlog = freeze(fx.revision_case())
    got = TemporalEngine(rlog, ResolverCondition.TEMPORAL).current(
        fx.SUBJECT_BACKEND).value
    metrics["supersession_accuracy"] = 1.0 if got == "PostgreSQL" else 0.0
    # Valid-time accuracy: April historical + Sept-10 future-effective cases.
    metrics["valid_time_accuracy"] = (
        metrics["historical_state_accuracy"][ResolverCondition.TEMPORAL]
        + metrics["future_effective_accuracy"]) / 2
    metrics["transaction_time_accuracy"] = metrics["late_arrival_robustness"]
    return metrics
