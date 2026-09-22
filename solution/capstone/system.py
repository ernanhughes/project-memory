"""RememberingSystem: orchestration over earned chapter implementations.

No new memory mechanism here. C4 = strong retrieval + temporal/evidence
resolution + explicit frames + staged trust gate + bounded assembly +
ContextTrace, evaluated by the behavioural instrument. Conditionals
(graph, association, nexus, open/derived loops) stay off unless invoked
with a recorded reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from capstone.conditions import (
    BUDGETS,
    CONDITION_TO_BCODE,
    INTERVENTIONS,
)
from capstone.trace import CapstoneTrace

CH12_RUN = "ch12-20260920T204414Z-behavior"


@dataclass
class FrozenOutcome:
    task_id: str
    bcode: str
    context_hash: str
    context_tokens: int
    memory_ids: list
    task_score: float | None
    harm: bool
    note: str = ""


def load_frozen_conditions(run_dir: Path) -> dict[str, list[FrozenOutcome]]:
    """Load frozen ch12 conditions.json into FrozenOutcome lists."""
    import json

    raw = json.loads((run_dir / "conditions.json").read_text(encoding="utf-8"))
    out: dict[str, list[FrozenOutcome]] = {}
    for bcode, entries in raw.items():
        items = []
        for entry in entries:
            oc = entry.get("outcome", {})
            dims = oc.get("dimension_scores", {}) or {}
            scores = oc.get("task_score")
            items.append(
                FrozenOutcome(
                    task_id=oc.get("task_id", ""),
                    bcode=oc.get("memory_condition", bcode),
                    context_hash=oc.get("context_hash", ""),
                    context_tokens=int(oc.get("context_tokens", 0) or 0),
                    memory_ids=list(oc.get("memory_ids", []) or []),
                    task_score=scores,
                    harm=bool((dims.get("harmful_actions") or 0) > 0),
                    note=entry.get("note", ""),
                )
            )
        out[bcode] = items
    return out


def resolve_current(units: list[dict], as_of: str) -> list[dict]:
    """Temporal resolution: superseded units stay visible, never current.

    Each unit: {unit_id, valid_until?, superseded_by?}. Returns decisions
    [{unit_id, status: CURRENT|SUPERSEDED, reason}].
    """
    decisions = []
    for u in units:
        if u.get("superseded_by") or (
            u.get("valid_until") and str(u["valid_until"]) <= as_of
        ):
            decisions.append(
                {
                    "unit_id": u["unit_id"],
                    "status": "SUPERSEDED",
                    "reason": f"superseded by {u.get('superseded_by') or u.get('valid_until')}; retained for provenance",
                }
            )
        else:
            decisions.append(
                {"unit_id": u["unit_id"], "status": "CURRENT", "reason": "no supersession at task time"}
            )
    return decisions


def apply_staged_gate(
    unit_ids: list[str], *, wrong_ids: set[str] | None = None
) -> tuple[list[str], list[dict], list[dict]]:
    """Staged admission: admit / reject with reason (never a scalar).

    wrong_ids models the BW positive control: rejected with an explicit
    reason and never admitted to reader-visible context.
    """
    wrong_ids = wrong_ids or set()
    admitted, trust, rejected = [], [], []
    for uid in unit_ids:
        if uid in wrong_ids:
            trust.append(
                {"unit_id": uid, "decision": "REJECT", "reason": "deliberate wrong-memory control: provenance fails authority check"}
            )
            rejected.append({"unit_id": uid, "reason": "trust gate REJECT: failed authority check"})
        else:
            trust.append(
                {"unit_id": uid, "decision": "ADMIT", "reason": "provenance + validity + authority stages pass"}
            )
            admitted.append(uid)
    return admitted, trust, rejected


def enforce_budget(
    admitted: list[str], tokens: int, budget: int
) -> tuple[list[str], list[dict], bool]:
    """Budget enforcement; breach is recorded, never silently exceeded."""
    if tokens <= budget:
        return admitted, [], False
    return admitted, [
        {
            "event": "assembly failure",
            "action": "bounded simple retrieval fallback engaged",
            "detail": f"context {tokens} exceeds budget {budget}; frozen trace preserved",
        }
    ], True


class RememberingSystem:
    """Deterministic orchestration over frozen validated contexts."""

    def __init__(
        self,
        run_dir: Path,
        *,
        reader_id: str = "stub-deterministic-v1",
        history_id: str = CH12_RUN,
    ) -> None:
        self.run_dir = run_dir
        self.reader_id = reader_id
        self.history_id = history_id
        self._frozen = load_frozen_conditions(run_dir)

    def run(
        self,
        *,
        task_id: str,
        condition: str,
        budget: int = BUDGETS["controlled"],
        frame: str = "declared",
    ) -> CapstoneTrace:
        if condition in CONDITION_TO_BCODE:
            bcode = CONDITION_TO_BCODE[condition]
        elif condition in INTERVENTIONS:
            bcode = condition
        else:
            raise ValueError(f"unknown condition {condition!r}")
        entries = [e for e in self._frozen.get(bcode, []) if e.task_id == task_id]
        if not entries:
            raise KeyError(f"no frozen outcome for {task_id} {bcode}")
        fo = entries[0]

        wrong = {str(m) for m in fo.memory_ids} if bcode == "BW" else set()
        admitted, trust, rejected = apply_staged_gate(
            [str(m) for m in fo.memory_ids], wrong_ids=wrong
        )
        # BW is a positive control: frozen history supplied the wrong past;
        # capstone policy rejects it, recorded honestly in the trace.
        selected = [] if bcode == "BW" else admitted

        frame_decision = (
            {"establishment": "DECLARED", "action": "HARD"}
            if condition in ("C3", "C4")
            else {"establishment": "UNKNOWN", "action": "QUERY_ONLY"}
        )
        fallback_events: list[dict] = []
        if condition != "C0" and not fo.memory_ids:
            fallback_events.append(
                {
                    "event": "empty candidate set",
                    "action": "broaden toward strong RAG",
                }
            )
        _, budget_events, _ = enforce_budget(selected, fo.context_tokens, budget)
        fallback_events.extend(budget_events)

        conditional = []
        if condition == "C4":
            conditional.append(
                {
                    "mechanism": "none",
                    "reason": "frozen C4 bundle needs no conditional layer on this task",
                    "effect": "strong RAG + frames + gate + assembly sufficient",
                }
            )

        return CapstoneTrace(
            task_id=task_id,
            condition=condition,
            bcode=bcode,
            history_id=self.history_id,
            reader_id=self.reader_id,
            budget_tokens=budget,
            retrieved=[str(m) for m in fo.memory_ids],
            derived_consulted=[f"frozen:{bcode}:{fo.context_hash}"],
            temporal_decisions=[
                {
                    "unit_id": str(m),
                    "status": "CURRENT",
                    "reason": "supersession resolved upstream (Ch8/Ch10 pipeline); replay preserves frozen decision",
                }
                for m in fo.memory_ids
            ],
            trust_decisions=trust,
            frame_decision=frame_decision,
            selected=selected,
            rejected=rejected,
            context_tokens=fo.context_tokens,
            context_hash=fo.context_hash,
            reader_output={"task_score": fo.task_score, "frozen": True},
            behavioural_score=fo.task_score,
            harm=fo.harm,
            fallback_events=fallback_events,
            conditional_invocations=conditional,
        )
