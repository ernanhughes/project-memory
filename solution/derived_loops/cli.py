"""CLI demo: show the triple gate on the full corpus_import scope."""

from __future__ import annotations

from . import fixtures as fx
from .baselines import run_condition
from .experiments import run_suite
from .metrics import score_task


def demo() -> str:
    task = next(t for t in fx.all_tasks() if t.task_id == "t-full-scope")
    lines = [f"SCOPE {task.scope}", f"STANDPOINT {task.standpoint}", ""]
    suite = run_suite()
    for condition in ("unconstrained", "staged", "oracle", "abstain"):
        score = score_task(task, run_condition(condition, task))
        agg = suite["conditions"][condition]["aggregate"]
        lines.append(
            f"{condition}: admitted={score['admitted']} "
            f"prec={score['inferred_precision']} "
            f"rec={score['inferred_recall']} "
            f"harmful={score['harmful_listed']}")
        lines.append(
            f"  aggregate macro={agg['mean_inferred_precision']}/"
            f"{agg['mean_inferred_recall']} "
            f"micro={agg['micro_precision']}/{agg['micro_recall']} "
            f"harmful_tasks={agg['tasks_with_harmful']} "
            f"abstention={agg['abstention_rate']}")
    lines.append("")
    lines.append("STAGED TRACE (full scope):")
    for d in run_condition("staged", task):
        lines.append(f"  {d.candidate_id} admitted={d.admitted} "
                     f"stage={d.stage_failed} reason={d.reason}")
    lines.append("")
    b = suite["backtest"]
    lines.append(f"BACKTEST {b['candidate']}: gain={b['primary_gain']} "
                 f"promoted={b['promoted']} breaches={b['breaches']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(demo())
