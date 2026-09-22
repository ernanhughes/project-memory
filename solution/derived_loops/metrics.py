"""Metrics: inferred-consequence precision/recall, abstention, evidence.

Inferred-consequence precision/recall are scored separately from
explicit-task metrics and published per fixture before any aggregate.
Harmful-recommendation rate is reported separately and never averaged
into precision: breaking a recorded commitment is not commensurable
with an ordinary false positive.
"""

from __future__ import annotations

from . import fixtures as fx
from .model import GateDecision, ScopeTask


def _safe(num: float, den: float) -> float | None:
    """Undefined denominators stay undefined: null, never a semantic zero."""
    return round(num / den, 4) if den else None


def score_task(task: ScopeTask,
               decisions: list[GateDecision]) -> dict:
    by_id = {d.candidate_id: d for d in decisions}
    genuine = fx.ledger_genuine(task)
    harmful = fx.ledger_harmful(task)
    by_cand = {c.candidate_id: c for c in task.candidates}

    admitted = {cid for cid, d in by_id.items() if d.admitted}
    tp = admitted & genuine
    fp = admitted - genuine
    fn = genuine - admitted

    # Evidence correctness: admitted genuine candidates must cite both
    # legs; admitted non-genuine candidates fail evidence by definition
    # here because the fixture ledger adjudicates the triple.
    evidence_ok = sum(1 for cid in tp
                      if len(by_id[cid].legs_cited) == 2)
    harmful_listed = sorted(admitted & harmful)
    # Abstention correct only on trap-only tasks with zero genuine loops.
    trap_only = not genuine
    abstained = not admitted
    abstention_ok = bool(trap_only and abstained)

    # Explicit obligations must never be reported as derived.
    explicit_leak = sorted(
        c for c in task.explicit_obligations
        if c in {by_cand[cid].subject for cid in admitted})

    return {
        "task_id": task.task_id,
        "genuine": sorted(genuine),
        "admitted": sorted(admitted),
        "true_positives": sorted(tp),
        "false_positives": sorted(fp),
        "false_negatives": sorted(fn),
        "inferred_precision": _safe(len(tp), len(admitted)),
        "inferred_recall": _safe(len(tp), len(genuine)),
        "abstention_ok": abstention_ok,
        "trap_only": trap_only,
        "evidence_correct": evidence_ok,
        "evidence_total": len(tp),
        "evidence_correctness": _safe(evidence_ok, len(tp)),
        "harmful_listed": harmful_listed,
        "harmful_rate": _safe(len(harmful_listed), len(admitted)),
        "explicit_leak": explicit_leak,
        "stage_failures": {d.candidate_id: d.stage_failed
                           for d in decisions if not d.admitted},
    }


def aggregate(task_scores: list[dict]) -> dict:
    prec_defined = [s["inferred_precision"] for s in task_scores
                    if s["inferred_precision"] is not None]
    rec_defined = [s["inferred_recall"] for s in task_scores
                   if s["inferred_recall"] is not None]
    tp = sum(len(s["true_positives"]) for s in task_scores)
    admitted = sum(len(s["admitted"]) for s in task_scores)
    genuine = sum(len(s["genuine"]) for s in task_scores)
    harm_tasks = sum(1 for s in task_scores if s["harmful_listed"])
    abst_tasks = [s for s in task_scores if s["trap_only"]]
    abst_ok = sum(1 for s in abst_tasks if s["abstention_ok"])
    ev_ok = sum(s["evidence_correct"] for s in task_scores)
    ev_tot = sum(s["evidence_total"] for s in task_scores)
    return {
        "tasks": len(task_scores),
        "positive_tasks": len(rec_defined),
        "mean_inferred_precision": round(
            sum(prec_defined) / len(prec_defined), 4)
        if prec_defined else None,
        "mean_inferred_recall": round(
            sum(rec_defined) / len(rec_defined), 4)
        if rec_defined else None,
        "micro_precision": _safe(tp, admitted),
        "micro_recall": _safe(tp, genuine),
        "tasks_with_harmful": harm_tasks,
        "harmful_task_rate": _safe(harm_tasks, len(task_scores)),
        "abstention_tasks": len(abst_tasks),
        "abstention_correct": abst_ok,
        "abstention_rate": _safe(abst_ok, len(abst_tasks)),
        "evidence_correctness": _safe(ev_ok, ev_tot),
    }
