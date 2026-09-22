"""Real-project transfer runner (§52-53, §79): time-locked, adjudicated.

Five repository questions at commit 4797720. M0 (no memory) vs Mm
(frozen verbatim excerpt). Scores strictly separate from controlled
fixtures. Appends real-transfer.json into the canonical run dir.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "solution"))

from behavior_eval import prompts as P  # noqa: E402
from behavior_eval.real_transfer import (  # noqa: E402
    EXCERPTS,
    TASKS,
    TIME_LOCK_COMMIT,
    TIME_LOCK_STANDPOINT,
    grade_transfer,
    render_task,
)
from behavior_eval.runner import ReaderClient, capped_ask  # noqa: E402
from context_frames.reader import SYSTEM_PROMPT, Reader  # noqa: E402

# Parsing schema admits the documented TRANSFER_ALIASES spellings;
# grade_transfer normalises them before scoring.
SCHEMA = ("REPORT_BLOCKERS", "REPORT_RESULT", "ADOPT_MECHANISM",
          "REJECT_MECHANISM", "REJECT_PROPOSAL",
          "IMPLEMENT_ABSTENTION_PATH")


def main() -> int:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    model = sys.argv[2] if len(sys.argv) > 2 else "llama3.1:8b"
    reader = Reader(model=model)
    if not reader.available():
        print("no live reader")
        return 2
    results: dict = {"time_lock_commit": TIME_LOCK_COMMIT,
                     "standpoint": TIME_LOCK_STANDPOINT,
                     "reader": f"{model}@t0",
                     "tasks": {}}
    for task_id, spec in TASKS.items():
        objective, question, expected = render_task(task_id, True)
        excerpt = EXCERPTS[spec["excerpt"]]
        task_rows = {}
        for cond, context in (
                ("M0", ""),
                ("Mm", f"[{excerpt['source']}]\n{excerpt['text']}")):
            prompt = (f"Work objective: {objective}\n\nPresent task "
                      f"state:\n{question}\n\n")
            if context.strip():
                prompt += f"Project evidence:\n\n{context}\n\n"
            else:
                prompt += ("Project evidence: none supplied.\n\n")
            from behavior_eval.prompts import action_docs
            from behavior_eval.real_transfer import TRANSFER_EXAMPLES
            fields = {
                "rt-runs": ("REPORT_BLOCKERS",),
                "rt-gap": ("REPORT_BLOCKERS", "REPORT_RESULT"),
                "rt-promote": ("ADOPT_MECHANISM", "REJECT_MECHANISM",
                               "REJECT_PROPOSAL"),
                "rt-frame": ("REPORT_BLOCKERS",
                             "IMPLEMENT_ABSTENTION_PATH"),
                "rt-metric": ("REPORT_BLOCKERS",),
            }[task_id]
            prompt += ("Allowed actions (name with its parameters — "
                       "fill values from the question and the evidence):\n"
                       "%s\n\n" % action_docs(fields))
            prompt += (
                'Respond with a brief rationale, then exactly one ```json '
                'block with an "actions" list. Field shape (values shown '
                'are placeholders that score 0 — fill genuine values):\n'
                '```json\n{"actions": [%s]}\n```'
                % TRANSFER_EXAMPLES[task_id])
            answer = capped_ask(model, reader.host, SYSTEM_PROMPT, prompt)
            actions, parse_ok = P.parse_actions(answer, SCHEMA)
            graded = (grade_transfer(task_id, actions)
                      if parse_ok else {"field_scores": {},
                                        "task_score": 0.0,
                                        "reported": {}})
            task_rows[cond] = {
                "parse_ok": parse_ok,
                "actions": actions,
                "answer": answer[:2000],
                "expected": {k: v for k, v in expected.items()},
                "field_scores": graded["field_scores"],
                "task_score": graded["task_score"]}
            print(task_id, cond, graded["task_score"], actions)
        results["tasks"][task_id] = task_rows
    payload = json.dumps(results, indent=2)
    if outdir is not None:
        (outdir / "real-transfer.json").write_text(payload)
        print(f"wrote {outdir / 'real-transfer.json'}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
