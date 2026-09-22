"""Demo: the counterfactual test on one task (live reader required)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from behavior_eval import contexts as C  # noqa: E402
from behavior_eval import prompts as P  # noqa: E402
from behavior_eval import runner as R  # noqa: E402
from behavior_eval.experiments import PLAN, cleanup_entry  # noqa: E402
from behavior_eval.tasks import task_by_id  # noqa: E402
from context_frames.reader import Reader  # noqa: E402


def demo(task_id: str = "fix-store") -> str:
    reader = Reader()
    if not reader.available():
        return "no live reader reachable; demo needs Ollama llama3.1:8b"
    task = task_by_id(task_id)
    texts = C.corpus_texts()
    plan = PLAN[task_id]
    lines = [f"TASK {task.work_objective}", ""]
    for condition in ("B0", "B2", "B4", "BA", "BR"):
        if task_id == "corpus-cleanup" and condition == "B2":
            continue
        if task_id == "corpus-cleanup":
            entry = cleanup_entry(
                {"B0": "B0", "B4": "B4", "BA": "BA", "BR": "BR"}[condition])
        else:
            entry = C.finalize(C.build_condition(
                plan["ch10"], condition, texts, task.decisive_units,
                plan["wrong"], ch10_task=plan["ch10"]))
        prompt = P.build_prompt(task, entry["context"])
        answer = reader.ask(prompt)
        actions, parse_ok = P.parse_actions(answer, task.action_schema)
        acts = [R.Action.from_dict(a) for a in actions]
        world = R.run_actions(R.initial_world(task), acts)
        from behavior_eval import graders
        scored = graders.grade(task, acts, world) if parse_ok else {}
        lines.append(f"{condition}: parse_ok={parse_ok} "
                     f"actions={[a.action_type for a in acts]} "
                     f"scores={scored}")
    lines.append("")
    lines.append("BEHAVIOR DELTA: compare B0 actions against B4 actions; "
                 "BA/BR show the decisive-memory intervention.")
    return "\n".join(lines)


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "fix-store"
    print(demo(task))
