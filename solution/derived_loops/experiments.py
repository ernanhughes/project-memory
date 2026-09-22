"""Suite runner: every condition over every scope task, frozen."""

from __future__ import annotations

from . import fixtures as fx
from .baselines import CONDITIONS, run_condition
from .backtest import evaluate_candidate
from .metrics import aggregate, score_task
from .model import GATE_VERSION


def run_suite() -> dict:
    tasks = fx.all_tasks()
    per_condition: dict[str, dict] = {}
    for condition in CONDITIONS:
        scores = [score_task(t, run_condition(condition, t)) for t in tasks]
        per_condition[condition] = {"scores": scores,
                                    "aggregate": aggregate(scores)}
    # Backtest: the tempting loosening (drop the cancelling-evidence
    # leg) against the frozen staged gate.
    backtest = evaluate_candidate(
        per_condition["staged"]["aggregate"],
        per_condition["no-cancel"]["aggregate"])
    backtest.update({"candidate": "v2-drop-cancelling-leg",
                     "rationale": "recover the deferred-docs candidate; "
                                  "locally correct, globally harmful"})
    return {"suite": "E-11-derived-loops",
            "gate_version": GATE_VERSION,
            "standpoint": fx.all_tasks()[0].standpoint,
            "conditions": per_condition,
            "backtest": backtest}
