"""Real-project transfer: time-locked, manually adjudicated (§52-53).

Five tasks about the actual repository at the frozen commit. Memory
conditions supply short verbatim excerpts (frozen strings with source
file + commit); the no-memory condition supplies nothing. Scores are
kept strictly separate from controlled-fixture scores (§79).

Time lock: commit 4797720, standpoint 2026-09-20T12:00:00Z.
Adjudicated by reading the cited files on 2026-09-20; disagreements
would be preserved here, of which there are currently none.
"""

from __future__ import annotations

TIME_LOCK_COMMIT = "4797720"
TIME_LOCK_STANDPOINT = "2026-09-20T12:00:00Z"

EXCERPTS = {
    "arch-status": {
        "source": "planning/book-architecture.md @ 4797720",
        "text": (
            "Chapter 10 status 2026-09-20: redirected and run. Verdict "
            "type C: context selection improved substantially, answer "
            "correctness did not follow.\n"
            "Chapter 11 status 2026-09-20: rebuilt and run. Verdict type "
            "A on fixture evidence. Canonical run "
            "ch11-20260920T171039Z-derived-loops; "
            "ch11-20260920T165907Z preserved as historical evidence.\n"
            "Chapter 14 status 2026-09-20: built and run. Verdict Type B "
            "profile with a Type C headline."),
    },
    "oracle-audit": {
        "source": "planning/chapter-14-oracle-audit.md @ 4797720",
        "text": (
            "CO-content 587 counted tokens at required recall 1.0. "
            "CO-auditable 696 counted tokens with contradiction and "
            "licences restored. Best practical assembled context (A6) "
            "1156 counted tokens at required recall 0.90. The fair "
            "oracle gap is 696 versus 1156, narrower than the raw "
            "587 versus 1161."),
    },
    "backtest": {
        "source": ("experiments/benchmark/runs/"
                   "ch14-20260920T174259Z-context-assembly/"
                   "policy-backtest.json @ 4797720"),
        "text": (
            "Candidate v2-drop-refutes-first: base required recall "
            "0.5758, candidate 0.6061; base tokens 452.7, candidate "
            "443.5 (delta -9.2). Breach: contradiction_preservation "
            "1.0 -> 0.1429. Promoted: false."),
    },
    "frame-hazard": {
        "source": "content/books/memory/10-chapter.md @ 4797720",
        "text": (
            "With the work type deliberately misassigned, must-include "
            "recall on the architectural review falls from 0.833 to "
            "0.333. A prose-finishing task read as implementation "
            "review scores 0.000. The remedy these numbers point to is "
            "that a work frame needs an abstention path of its own: "
            "conditioning would weaken as frame establishment degrades, "
            "falling back toward query-only retrieval. The measured "
            "harm argues for it; this chapter did not build or test it."),
    },
    "metric-rule": {
        "source": "planning/chapter-11-metric-audit.md @ 4797720",
        "text": (
            "Preferred repair: per-task precision undefined/null when "
            "admitted = 0; per-task recall undefined/null when genuine "
            "= 0. A zero denominator never becomes a semantic zero. "
            "Abstention stays a separate metric over zero-positive "
            "trap tasks."),
    },
}

# task_id -> {question, excerpt_key, expected structured fields}.
# Expected values adjudicated from the excerpts above.
TASKS = {
    "rt-runs": {
        "question": ("Which of Chapters 10, 11 and 14 have canonical "
                     "frozen runs, and what is the canonical Chapter 11 "
                     "run ID?"),
        "excerpt": "arch-status",
        "schema": ("REPORT_BLOCKERS",),
        "expected": {"ch10": True, "ch11": True, "ch14": True,
                     "ch11_canonical": "ch11-20260920T171039Z"},
    },
    "rt-gap": {
        "question": ("What fair-oracle gap does Chapter 14 report, in "
                     "counted tokens (auditable oracle versus best "
                     "practical assembled context)?"),
        "excerpt": "oracle-audit",
        "schema": ("REPORT_BLOCKERS",),
        "expected": {"oracle_tokens": 696, "practical_tokens": 1156},
    },
    "rt-promote": {
        "question": ("A drop-policy revision saves 9.2 tokens and nudges "
                     "recall upward, but contradiction preservation falls "
                     "from 1.00 to 0.14. Promote it?"),
        "excerpt": "backtest",
        "schema": ("ADOPT_MECHANISM", "REJECT_MECHANISM"),
        # "~" prefix: substring match (free-text reason graders cannot
        # demand exact phrasing without becoming a paraphrase test).
        "expected": {"promote": False,
                     "reason": "~contradiction"},
    },
    "rt-frame": {
        "question": ("A prose-finishing task misread as implementation "
                     "review scores recall 0.000. Per Chapter 10, what "
                     "must the frame provide for such cases?"),
        "excerpt": "frame-hazard",
        "schema": ("REPORT_BLOCKERS",),
        "expected": {"abstention_path": True, "fallback": "query-only"},
    },
    "rt-metric": {
        "question": ("A new trap-only fixture has zero genuine positives "
                     "and the system abstains on all of them. Under the "
                     "book's repaired rule, what per-task precision and "
                     "recall values are recorded for that fixture?"),
        "excerpt": "metric-rule",
        "schema": ("REPORT_BLOCKERS",),
        "expected": {"precision": None, "recall": None},
    },
}


def render_task(task_id: str, with_memory: bool) -> tuple[str, str, dict]:
    """Return (objective, present_state, expected).

    Memory excerpt is supplied as the context by the caller; this
    returns the question text. present_state carries no excerpt text
    so M0/Mm differ only in supplied memory (§54: no backdoor).
    """
    spec = TASKS[task_id]
    objective = "Answer the repository question from supplied evidence."
    return objective, spec["question"], spec["expected"]


# Transfer field examples: shape demonstrations with neutralized
# values (false/0.0/ADOPT-shape), so copying them verbatim scores 0.
# Controlled prompts carry no examples at all (prompt v2); transfer
# tasks keep these because the report FIELDS are the task structure
# and models under-specify actions without them (measured: removing
# them collapsed transfer field completion). Values are neutralized
# and unit-tested to score 0 when copied.
TRANSFER_EXAMPLES = {
    "rt-runs": ('{"action_type": "REPORT_BLOCKERS", "ch10": false, '
                '"ch11": false, "ch14": false, '
                '"ch11_canonical": "EXAMPLE-ID-STRING"}'),
    "rt-gap": ('{"action_type": "REPORT_BLOCKERS", "oracle_tokens": 0, '
               '"practical_tokens": 0}'),
    "rt-promote": ('{"action_type": "ADOPT_MECHANISM", '
                   '"name": "EXAMPLE-POLICY", '
                   '"reason": "EXAMPLE-REASON"}'),
    "rt-frame": ('{"action_type": "REPORT_BLOCKERS", '
                 '"abstention_path": false, "fallback": "EXAMPLE-VALUE"}'),
    "rt-metric": ('{"action_type": "REPORT_BLOCKERS", "precision": 0.0, '
                  '"recall": 0.0}'),
}

# Action-type aliases observed in frozen outputs, applied uniformly
# and unit-tested. Each alias was used by the reader with the same
# verdict/report intent as the canonical type; accepting them is a
# documented parsing tolerance, not per-task score tuning.
TRANSFER_ALIASES = {
    # Reporting looked-up values (observed on rt-gap).
    "REPORT_RESULT": "REPORT_BLOCKERS",
    # Rejecting a policy revision (observed on rt-promote Mm).
    "REJECT_PROPOSAL": "REJECT_MECHANISM",
    # Describing the frame remedy (observed on rt-frame Mm).
    "IMPLEMENT_ABSTENTION_PATH": "REPORT_BLOCKERS",
}


def grade_transfer(task_id: str, actions: list[dict]) -> dict:
    """Deterministic grading against adjudicated values.

    TRANSFER_ALIASES normalise observed action-type synonyms before
    grading. "~"-prefixed expectations are substring matches.
    """
    expected = TASKS[task_id]["expected"]
    reported: dict = {}
    for action in actions:
        atype = TRANSFER_ALIASES.get(action.get("action_type"),
                                     action.get("action_type"))
        # A verdict action is itself the promote/ship/hold decision:
        # REJECT_MECHANISM means promote=False, ADOPT means True.
        if atype == "REJECT_MECHANISM":
            reported.setdefault("promote", False)
        elif atype == "ADOPT_MECHANISM":
            reported.setdefault("promote", True)
        for key, value in action.items():
            if key != "action_type":
                reported[key] = value
    scores = {}
    for key, want in expected.items():
        present = key in reported
        got = reported.get(key)
        if isinstance(want, str) and want.startswith("~"):
            needle = want[1:].lower()
            scores[key] = 1.0 if needle in str(got).lower() else 0.0
        elif isinstance(want, bool):
            scores[key] = 1.0 if got is want else 0.0
        elif want is None:
            # Omission is not a null: stating the repaired rule means
            # emitting the keys with null values. (A run that omits
            # both keys scored 1.0 here before this fix.)
            scores[key] = 1.0 if (present and got is None) else 0.0
        elif isinstance(want, (int, float)) and not isinstance(want, bool):
            scores[key] = 1.0 if got == want else 0.0
        else:
            scores[key] = (1.0 if str(got).strip().lower()
                           in str(want).strip().lower()
                           or str(want).strip().lower()
                           in str(got).strip().lower() else 0.0)
    task_score = (round(sum(scores.values()) / len(scores), 4)
                  if scores else None)
    return {"field_scores": scores, "task_score": task_score,
            "reported": reported}
