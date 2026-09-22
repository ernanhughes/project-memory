"""Backtest: a candidate gate is an immutable version, replayed over
every task, promoted only if the primary metric improves with no gate
breached. Mirrors context_frames/backtest.py so the operating-point
discipline transfers.
"""

from __future__ import annotations

PRIMARY = "mean_inferred_precision"
GATES = (
    ("harmful_task_rate", "no_worse", 0.0),
    ("mean_inferred_recall", "no_worse_than", 0.15),
    ("abstention_rate", "no_worse", 0.0),
)


def evaluate_candidate(baseline: dict, candidate: dict) -> dict:
    """Compare one candidate aggregate against the frozen baseline."""
    breaches = []
    for metric, rule, tol in GATES:
        b, c = baseline[metric], candidate[metric]
        if metric == "harmful_task_rate":
            if c > b + 1e-9:
                breaches.append(f"{metric}: {b} -> {c}")
        elif rule == "no_worse" and c < b - 1e-9:
            breaches.append(f"{metric}: {b} -> {c}")
        elif rule == "no_worse_than" and c < b - tol - 1e-9:
            breaches.append(f"{metric}: {b} -> {c} (tol {tol})")
    primary_gain = round(candidate[PRIMARY] - baseline[PRIMARY], 4)
    promoted = primary_gain > 0 and not breaches
    return {"primary": PRIMARY,
            "primary_gain": primary_gain,
            "breaches": breaches,
            "promoted": promoted}
