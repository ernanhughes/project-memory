"""Policy revision by replay, with explicit regression gates.

When a frozen run shows a selection failure, the tempting repair is to
edit the frame until that case passes. The book's own methodology
forbids it: a change to policy is a change to a measured variable, so it
is proposed, replayed over every existing task, and promoted only if a
declared primary metric improves without breaching a declared gate.

Nothing here learns online. A candidate frame is an immutable version, a
backtest is a frozen comparison, and promotion is a recorded decision.
That ordering is what makes the adaptation inspectable rather than a
system quietly revising what it considers important.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from . import fixtures as fx
from .model import ProjectFrame

PRIMARY = "must_include_recall"
GATES = (
    # metric, direction, tolerance -- a proposal breaching any gate is
    # rejected however much the primary metric improved.
    ("harmful_admission", "no_worse", 0.0),
    ("cross_project_leakage", "no_worse", 0.0),
    ("context_precision", "no_worse_than", 0.02),
    ("bundle_tokens", "within_budget", 0.0),
)


@dataclass
class Proposal:
    name: str
    frame: ProjectFrame
    rationale: str


def propose(base: ProjectFrame) -> list[Proposal]:
    """Candidate revisions, each motivated by a named observed failure."""
    table = dict(base.evidence_preferences)
    proposals: list[Proposal] = []

    # Observation: under architecture_review the chapter's own
    # experiment-pending marker ranked last among preferred classes and
    # lost to the budget, although the decision turns on it.
    arch = list(table[fx.WT_ARCHITECTURE])
    arch.remove("chapter_prose")
    arch.insert(2, "chapter_prose")
    revised = dict(table)
    revised[fx.WT_ARCHITECTURE] = tuple(arch)
    proposals.append(Proposal(
        "v2-prose-earlier",
        replace(base, version="v2",
                evidence_preferences=tuple(revised.items())),
        "chapter_prose raised to rank 3 for architecture_review: the "
        "chapter under review is evidence about itself"))

    # Observation: under implementation_review the measurement contract
    # was ruled out as a class the work type does not list, although the
    # question concerned what the context system should measure.
    impl = list(table[fx.WT_IMPLEMENTATION]) + ["measurement_contract"]
    revised2 = dict(table)
    revised2[fx.WT_IMPLEMENTATION] = tuple(impl)
    proposals.append(Proposal(
        "v2-contract-in-implementation",
        replace(base, version="v2b",
                evidence_preferences=tuple(revised2.items())),
        "measurement_contract added to implementation_review: improving a "
        "system requires knowing how it is scored"))

    # Observation: two required units were never candidates because the
    # class pull guaranteed only three per class.
    proposals.append(Proposal(
        "v2-wider-class-pull",
        replace(base, version="v2c", class_pull_width=5),
        "class pull widened from three to five candidates per preferred "
        "class: required evidence was never reaching the pool"))

    both = dict(revised)
    both[fx.WT_IMPLEMENTATION] = tuple(impl)
    proposals.append(Proposal(
        "v3-combined",
        replace(base, version="v3", class_pull_width=5,
                evidence_preferences=tuple(both.items())),
        "all three revisions together"))
    return proposals


def _mean(rows: list[dict], key: str) -> float:
    return round(sum(r[key] for r in rows) / len(rows), 4) if rows else 0.0


def backtest(harness, base: ProjectFrame, condition: str = "C6") -> dict:
    """Replay every task of the project under each proposed frame."""
    tasks = [t for t in fx.all_tasks() if t.project_id == base.project_id]

    def evaluate(frame: ProjectFrame, suffix: str) -> dict:
        rows = []
        per_task = {}
        for task in tasks:
            scored, bundle, _ = harness.score(condition, task, frame=frame,
                                              suffix=suffix)
            rows.append(scored)
            per_task[task.task_id] = {
                k: scored[k] for k in
                (PRIMARY, "context_precision", "harmful_admission",
                 "cross_project_leakage", "bundle_tokens")}
        return {
            "per_task": per_task,
            PRIMARY: _mean(rows, PRIMARY),
            "context_precision": _mean(rows, "context_precision"),
            "harmful_admission": _mean(rows, "harmful_admission"),
            "cross_project_leakage": _mean(rows, "cross_project_leakage"),
            "bundle_tokens": _mean(rows, "bundle_tokens"),
            "over_budget": any(r["bundle_tokens"] > r["budget_tokens"]
                               for r in rows),
        }

    baseline = evaluate(base, "-bt-base")
    results = []
    for i, proposal in enumerate(propose(base)):
        candidate = evaluate(proposal.frame, f"-bt-{i}")
        breaches = []
        for metric, direction, tolerance in GATES:
            if direction == "no_worse":
                if candidate[metric] > baseline[metric]:
                    breaches.append(f"{metric} rose to {candidate[metric]}")
            elif direction == "no_worse_than":
                if candidate[metric] < baseline[metric] - tolerance:
                    breaches.append(
                        f"{metric} fell to {candidate[metric]} "
                        f"from {baseline[metric]}")
            elif direction == "within_budget" and candidate["over_budget"]:
                breaches.append("bundle exceeded the budget")
        delta = round(candidate[PRIMARY] - baseline[PRIMARY], 4)
        decision = "PROMOTE" if (delta > 0 and not breaches) else "REJECT"
        results.append({
            "proposal": proposal.name, "rationale": proposal.rationale,
            "frame_version": proposal.frame.version,
            "baseline": {k: baseline[k] for k in
                         (PRIMARY, "context_precision", "harmful_admission",
                          "cross_project_leakage", "bundle_tokens")},
            "candidate": {k: candidate[k] for k in
                          (PRIMARY, "context_precision", "harmful_admission",
                           "cross_project_leakage", "bundle_tokens")},
            "primary_delta": delta, "gate_breaches": breaches,
            "decision": decision,
            "per_task": candidate["per_task"],
        })
    promoted = [r for r in results if r["decision"] == "PROMOTE"]
    return {"base_frame": base.frame_id(), "condition": condition,
            "primary_metric": PRIMARY,
            "gates": [{"metric": m, "direction": d, "tolerance": t}
                      for m, d, t in GATES],
            "baseline": {k: baseline[k] for k in
                         (PRIMARY, "context_precision", "harmful_admission",
                          "cross_project_leakage", "bundle_tokens")},
            "proposals": results,
            "promoted": [r["proposal"] for r in promoted],
            "rejected": [r["proposal"] for r in results
                         if r["decision"] == "REJECT"]}
