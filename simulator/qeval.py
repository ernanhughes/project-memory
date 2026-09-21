"""Question-task prompt, parse, and scoring (expansion, model-free parts).

Q-flow tasks ask the reader for artifact ids (Q1/Q2/Q3/Q5/recall),
a yes/no verdict (Q4), or an exact echo (irrelevant control).
Parsing is deterministic regex/substring matching; scoring is exact
(equality or containment), never graded by another model. Q6
selection scoring compares admitted sets against a ledger-derived
oracle set without any reader call.
"""

from __future__ import annotations

import re

ID_RE = re.compile(r"\b[a-z]+-\d+\b")

Q_PROMPT_IDS = (
    "Answer the question using ONLY the supplied project history.\n\n"
    "QUESTION: {text}\n\n"
    "STANDPOINT: {as_of} (ignore anything dated after this)\n\n"
    "PROJECT HISTORY:\n{context}\n\n"
    "Reply with the artifact ids that answer the question, one per "
    "line, each of the form xxx-NNN (for example session-014). "
    "List only ids, no other text.")

Q_PROMPT_YESNO = (
    "Answer the question using ONLY the supplied project history.\n\n"
    "QUESTION: {text}\n\n"
    "STANDPOINT: {as_of} (ignore anything dated after this)\n\n"
    "PROJECT HISTORY:\n{context}\n\n"
    "Reply with exactly one word: YES or NO. No other text.")

Q_PROMPT_ECHO = (
    "TASK: {text}\n\n"
    "PROJECT HISTORY:\n{context}\n\n"
    "Repeat exactly the requested string and nothing else.")


def build_q_prompt(task, context: str) -> str:
    if task.query_kind == "ids":
        template = Q_PROMPT_IDS
    elif task.query_kind == "yesno":
        template = Q_PROMPT_YESNO
    elif task.query_kind == "echo":
        template = Q_PROMPT_ECHO
    else:
        raise ValueError(f"unknown query kind {task.query_kind}")
    return template.format(text=task.text, as_of=task.as_of,
                           context=context)


def parse_ids(text: str) -> list[str]:
    seen = []
    for match in ID_RE.findall(text or ""):
        if match not in seen:
            seen.append(match)
    return seen


def parse_yesno(text: str) -> bool | None:
    found = re.findall(r"\b(yes|no)\b", (text or "").lower())
    if not found:
        return None
    return found[0] == "yes"


def score_qtask(task, response: str) -> dict:
    """Deterministic Q scoring. id tasks compare SETS (response
    ordering carries no meaning); yesno matches the boolean; echo
    requires substring presence."""
    if task.query_kind == "ids":
        predicted = parse_ids(response)
        expected = list(task.expected_ids)
        return {"task_score": 1.0 if set(predicted) == set(expected)
                else 0.0,
                "parsed": predicted, "expected": expected}
    if task.query_kind == "yesno":
        predicted = parse_yesno(response)
        expected = bool(task.expected_bool)
        return {"task_score": 1.0 if predicted is expected else 0.0,
                "parsed": predicted, "expected": expected}
    if task.query_kind == "echo":
        hit = task.expected_string in (response or "")
        return {"task_score": 1.0 if hit else 0.0,
                "parsed": (response or "")[:200],
                "expected": task.expected_string}
    raise ValueError(f"unknown query kind {task.query_kind}")


def precision_recall(predicted: set[str],
                     expected: set[str]) -> dict:
    """Q6 selection scoring: admitted set vs oracle set."""
    if not expected:
        return {"precision": None, "recall": None}
    if not predicted:
        return {"precision": None, "recall": 0.0}
    hit = predicted & expected
    return {"precision": round(len(hit) / len(predicted), 4),
            "recall": round(len(hit) / len(expected), 4)}
