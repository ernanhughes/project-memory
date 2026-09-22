"""Cross-query consistency analysis (proposed Chapter 2 extension).

Book §26: a memory system should not independently reconstruct
incompatible states from the same fixed history without acknowledging
uncertainty. This module profiles consistency mechanically:

- per-family answer harvesting across query modes;
- contradiction signatures between a decision answer and its negation
  window (expected_state present vs superseded_option unnegated);
- stability: same task, different modes — do the answers agree on the
  ledger-recorded state?

This lives in ``graph_memory`` (not ``memory_measurement``) because it is
a *proposed* instrument evolution (book §42): the chapter must earn it
before Chapter 2 adopts it. Nothing here changes existing scorers.

A profile, not a score: the output is per-family agreement rates plus the
concrete contradicting pairs for inspection. A single consistency number
would hide whether the system contradicts itself on decisions (harmful)
or merely varies background emphasis (benign).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\\s]", " ", text)
    return re.sub(r"\\s+", " ", text).strip()


_NEGATION_TOKENS = (
    "not", "n't", "never", "no", "without", "reject", "rejected",
    "rejects", "against", "instead", "declined", "refused", "abandoned",
    "ruled out",
)


def _states_unnegated(state: str, answer: str) -> bool:
    """True when the state is asserted without a nearby negation."""
    normalised = _normalize(answer)
    target = _normalize(state)
    at = normalised.find(target)
    if at < 0:
        return False
    window = normalised[max(0, at - 60):at]
    return not any(token in window.split() for token in _NEGATION_TOKENS)


@dataclass
class ConsistencyPair:
    task_a: str
    task_b: str
    mode_a: str
    mode_b: str
    kind: str  # "contradiction" | "agreement" | "incomparable"
    detail: str = ""


@dataclass
class ConsistencyProfile:
    pairs: list[ConsistencyPair] = field(default_factory=list)

    def agreement_rate(self) -> float | None:
        judged = [p for p in self.pairs if p.kind != "incomparable"]
        if not judged:
            return None
        agreed = sum(1 for p in judged if p.kind == "agreement")
        return agreed / len(judged)

    def contradictions(self) -> list[ConsistencyPair]:
        return [p for p in self.pairs if p.kind == "contradiction"]

    def to_dict(self) -> dict:
        return {
            "pairs": [p.__dict__ for p in self.pairs],
            "agreement_rate": self.agreement_rate(),
            "contradictions": len(self.contradictions()),
        }


def check_pair(
    answer_a: str,
    answer_b: str,
    expected_state: str | None,
    superseded_options: tuple[str, ...],
    task_a: str,
    task_b: str,
    mode_a: str,
    mode_b: str,
) -> ConsistencyPair:
    """Judge whether two answers over one history are compatible."""
    if not answer_a or not answer_b:
        return ConsistencyPair(
            task_a, task_b, mode_a, mode_b, "incomparable",
            "missing answer",
        )
    if expected_state:
        a_states = _states_unnegated(expected_state, answer_a)
        b_states = _states_unnegated(expected_state, answer_b)
        if a_states != b_states:
            return ConsistencyPair(
                task_a, task_b, mode_a, mode_b, "contradiction",
                f"expected state asserted in one answer only: {expected_state}",
            )
    for option in superseded_options:
        a_uses = _states_unnegated(option, answer_a)
        b_uses = _states_unnegated(option, answer_b)
        if a_uses != b_uses:
            return ConsistencyPair(
                task_a, task_b, mode_a, mode_b, "contradiction",
                f"superseded option treated differently: {option}",
            )
    if expected_state and _states_unnegated(expected_state, answer_a):
        return ConsistencyPair(
            task_a, task_b, mode_a, mode_b, "agreement",
            "both assert the recorded state",
        )
    return ConsistencyPair(
        task_a, task_b, mode_a, mode_b, "incomparable",
        "no recorded state asserted in either answer",
    )
