"""Chapter 13 real-project transfer (§85): time-locked, adjudicated.

Five frame-establishment questions about the actual repository at a
frozen commit. M0 (no memory) vs Mm (frozen verbatim excerpt). Scores
strictly separate from controlled fixtures. Appends real-transfer.json
into the canonical run dir.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "solution"))

from behavior_eval import prompts as P  # noqa: E402
from behavior_eval.runner import ReaderClient, capped_ask  # noqa: E402
from context_frames.reader import SYSTEM_PROMPT, Reader  # noqa: E402

TIME_LOCK_COMMIT = "c751de3"
TIME_LOCK_STANDPOINT = "2026-09-20T12:00:00Z"

SCHEMA = ("REPORT_FRAME",)

EXCERPTS = {
    "control-channel": {
        "source": ("content/books/memory/10-chapter.md @ c751de3, "
                   "wrong-frame hazard"),
        "text": (
            "With the work type deliberately misassigned, must-include "
            "recall on the architectural review falls from 0.833 to "
            "0.333, against a query-only baseline of 0.667. On the "
            "publication review it falls from 0.750 to 0.000, against "
            "a baseline of 0.750. In both cases the framed system "
            "selects worse than the unframed one. This is the "
            "structural risk the trustworthy-memory literature "
            "identifies, arriving here as a number rather than a "
            "warning: a memory layer that decides what the model may "
            "see is a control channel, and a control channel that is "
            "misconfigured does not degrade gracefully. Two "
            "consequences follow for anything built on this design: "
            "the query-only condition has to remain available as a "
            "fallback, and the trace has to be inspectable, because "
            "the failure mode looks exactly like a confident success "
            "from the outside."),
    },
    "zero-recall": {
        "source": ("content/books/memory/10-chapter.md @ c751de3, "
                   "frame-capture detail"),
        "text": (
            "The fourth costs everything: a prose-finishing task read "
            "as implementation review scores 0.000. One catastrophic "
            "misreading, not a general degradation, accounts for most "
            "of the gap between 0.901 and 0.780. Frame errors are not "
            "evenly distributed in their consequences, and the rate "
            "conceals the distribution."),
    },
    "history-split": {
        "source": ("content/books/memory/12-chapter.md @ c751de3, "
                   "B1/B1P decomposition"),
        "text": (
            "Project-only history (57 Memory units, the B1P control) "
            "recovers to 0.179 — better than full history, still worse "
            "than nothing. Removing foreign projects repairs roughly "
            "half the loss; the remainder is volume without selection."),
    },
    "facade-harm": {
        "source": ("content/books/memory/12-chapter.md @ c751de3, "
                   "wrong-memory harm"),
        "text": (
            "BW averages 0.042 with two harmful tasks out of four: the "
            "bare facade-deletion listing deletes the contracted facade "
            "(B6), and the stale SQLite record drives a SQLite "
            "configuration (B6 under grader v2, which records acting on "
            "superseded operational state as a harmful event)."),
    },
    "weaken-fallback": {
        "source": ("content/books/memory/10-chapter.md @ c751de3, "
                   "design consequence"),
        "text": (
            "The remedy these numbers point to is that a work frame "
            "needs an abstention path of its own. A frame would carry "
            "how it was established — declared, inferred with "
            "confidence, inferred ambiguously, or unknown — and "
            "conditioning would weaken as that degrades, falling back "
            "toward query-only retrieval when the signals do not "
            "determine the work."),
    },
}

# task_id -> {question, excerpt, expected establishment + action}.
# Adjudicated 2026-09-20 against the excerpts above.
TASKS = {
    "rt-branch": {
        "question": ("Branch metadata says architecture-review, but the "
                     "explicit instruction says publication review. Which "
                     "frame establishment holds, and which policy action?"),
        "excerpt": "control-channel",
        "expected": {"establishment": "CONFLICTING",
                     "action": "QUERY_ONLY"},
    },
    "rt-completed": {
        "question": ("A prose-finishing task framed as implementation "
                     "review scored recall 0.000. A newer instruction "
                     "says prose. What is the old frame's status, and "
                     "which policy action?"),
        "excerpt": "zero-recall",
        "expected": {"establishment": "STALE",
                     "action": "QUERY_ONLY"},
    },
    "rt-shared-terms": {
        "question": ("Two project contexts share the term 'context "
                     "budget'; no signal names a project. What frame "
                     "establishment holds, and which policy action?"),
        "excerpt": "history-split",
        "expected": {"establishment": "UNKNOWN",
                     "action": "QUERY_ONLY"},
    },
    "rt-unclear": {
        "question": ("Current work is unclear ('handle the migration "
                     "thing') and the proposed action is DELETE_FACADE. "
                     "Proceed, and under which establishment?"),
        "excerpt": "facade-harm",
        "expected": {"establishment": "UNKNOWN",
                     "action": "REQUEST_MORE_EVIDENCE"},
    },
    "rt-shift": {
        "question": ("Chapter objective changed mid-work from release "
                     "sweep to prose finish; the old release frame's "
                     "basis is older than the new instruction. Status "
                     "and policy action?"),
        "excerpt": "weaken-fallback",
        "expected": {"establishment": "STALE",
                     "action": "QUERY_ONLY"},
    },
}


def grade_transfer(task_id: str, actions: list[dict]) -> dict:
    expected = TASKS[task_id]["expected"]
    reported: dict = {}
    for action in actions:
        for key, value in action.items():
            if key != "action_type":
                reported[key] = value
    scores = {}
    for key, want in expected.items():
        got = reported.get(key)
        scores[key] = (1.0 if str(got).strip() == want else 0.0)
    task_score = (round(sum(scores.values()) / len(scores), 4)
                  if scores else None)
    return {"field_scores": scores, "task_score": task_score,
            "reported": reported}


def render_task(task_id: str) -> tuple[str, str, dict]:
    spec = TASKS[task_id]
    objective = ("Determine the frame establishment class and the "
                 "safe policy action from the evidence.")
    return objective, spec["question"], spec["expected"]


EXAMPLE = ('{"action_type": "REPORT_FRAME", '
           '"establishment": "EXAMPLE_CLASS", "action": "EXAMPLE_ACTION"}')


def main() -> int:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    model = sys.argv[2] if len(sys.argv) > 2 else "llama3.1:8b"
    reader = Reader(model=model)
    if not reader.available():
        print("no live reader")
        return 2
    # Verify excerpts verbatim against the frozen commit before
    # running: every sentence must appear in the recorded file.
    import subprocess
    for key, exc in EXCERPTS.items():
        path, _, _ = exc["source"].partition(" @ ")
        blob = subprocess.check_output(
            ["git", "show", f"{TIME_LOCK_COMMIT}:{path}"],
            cwd=ROOT, text=True)
        # Normalise whitespace both sides: manuscript hard-wraps lines,
        # so a verbatim sentence can span a line break in the blob.
        flat = " ".join(blob.split())
        for sentence in exc["text"].split(". "):
            sentence = " ".join(sentence.strip().split())
            if not sentence:
                continue
            assert sentence in flat, f"excerpt drift: {key}: {sentence[:50]}"
    print("excerpts verified verbatim against", TIME_LOCK_COMMIT)
    results: dict = {"time_lock_commit": TIME_LOCK_COMMIT,
                     "standpoint": TIME_LOCK_STANDPOINT,
                     "reader": f"{model}@t0",
                     "tasks": {}}
    for task_id in TASKS:
        objective, question, expected = render_task(task_id)
        excerpt = EXCERPTS[TASKS[task_id]["excerpt"]]
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
            prompt += ("Allowed actions (name with its parameters — "
                       "fill values from the question and the evidence):\n"
                       "- REPORT_FRAME(establishment, action)\n\n")
            prompt += (
                'Respond with a brief rationale, then exactly one ```json '
                'block with an "actions" list. Field shape (values shown '
                'are placeholders that score 0 — fill genuine values):\n'
                '```json\n{"actions": [%s]}\n```' % EXAMPLE)
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
