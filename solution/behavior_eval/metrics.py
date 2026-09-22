"""Deterministic behavioural metrics (§28-32, §71-72).

N/A is None, never zero. Macro averages run over applicable tasks;
micro is reported where meaningful (harmful-action rate, task
success). Paired deltas are per task; aggregates never hide
per-task signs (§29).
"""

from __future__ import annotations

from .model import BehaviorOutcome


def _mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def dimension_means(outcomes: list[BehaviorOutcome]) -> dict:
    dims: dict[str, list[float | None]] = {}
    for outcome in outcomes:
        for key, value in outcome.dimension_scores:
            dims.setdefault(key, []).append(value)
    return {dim: {"applicable": sum(1 for v in vals if v is not None),
                  "macro": _mean(vals)}
            for dim, vals in dims.items()}


def task_success_rate(outcomes: list[BehaviorOutcome]) -> dict:
    vals = [o.task_score for o in outcomes]
    return {"applicable": sum(1 for v in vals if v is not None),
            "macro": _mean(vals)}


def harmful_rate(outcomes: list[BehaviorOutcome]) -> dict:
    """Micro: harmful tasks / applicable tasks. Never averaged away."""
    vals = [o.score_of("harmful_actions") for o in outcomes]
    app = [v for v in vals if v is not None]
    bad = sum(1 for v in app if v > 0)
    return {"applicable": len(app), "harmful_tasks": bad,
            "micro": round(bad / len(app), 4) if app else None}


def paired_delta(base: BehaviorOutcome,
                 treated: BehaviorOutcome) -> dict:
    """score(treated) - score(base) on shared applicable dimensions."""
    deltas = {}
    for key, bval in base.dimension_scores:
        tval = treated.score_of(key)
        if bval is not None and tval is not None:
            deltas[key] = round(tval - bval, 4)
    btask, ttask = base.task_score, treated.task_score
    task_delta = (round(ttask - btask, 4)
                  if btask is not None and ttask is not None else None)
    changed = _behavior_changed(base, treated)
    return {"dimensions": deltas, "task_delta": task_delta,
            "behavior_changed": changed}


def _behavior_changed(base: BehaviorOutcome,
                      treated: BehaviorOutcome) -> bool:
    """Influence test: did the structured behaviour differ?"""
    return ([a.get("action_type") for a in base.structured_actions]
            != [a.get("action_type") for a in treated.structured_actions]
            or base.structured_actions != treated.structured_actions)


def directional_table(pairs: list[tuple[BehaviorOutcome, BehaviorOutcome]]
                      ) -> dict:
    """Directional influence reporting (review repair item 5).

    Complements the strict four-cell table, which only credits a
    contribution at perfect task success. Here every pair is
    classified by whether the structured actions changed and whether
    the score moved up, down, or stayed equal. A 0.00 -> 0.75 move
    counts as improvement here, not as failed-to-repair.
    """
    changed = improved = degraded = unchanged = 0
    for base, treated in pairs:
        comparison = paired_delta(base, treated)
        if comparison["behavior_changed"]:
            changed += 1
        delta = comparison["task_delta"]
        if delta is None:
            unchanged += 1
        elif delta > 0:
            improved += 1
        elif delta < 0:
            degraded += 1
        else:
            unchanged += 1
    return {"pairs": len(pairs), "behavior_changed": changed,
            "score_improved": improved, "score_degraded": degraded,
            "score_unchanged": unchanged}


def influence_table(pairs: list[tuple[BehaviorOutcome, BehaviorOutcome]]
                    ) -> dict:
    """Strict full-success contribution classification (§32).

    Labelled as such: only a treated score of 1.0 counts as a
    contribution here. Partial improvements (0.00 -> 0.75) are
    credited in directional_table, not here."""
    rows = []
    for base, treated in pairs:
        b_ok = (base.task_score or 0) >= 1.0
        t_ok = (treated.task_score or 0) >= 1.0
        if b_ok and t_ok:
            cell = "memory-not-shown-necessary"
        elif not b_ok and t_ok:
            cell = "beneficial-memory-contribution"
        elif b_ok and not t_ok:
            cell = "harmful-memory-contribution"
        else:
            cell = "memory-failed-to-repair"
        rows.append({"task": base.task_id,
                     "base": base.memory_condition,
                     "treated": treated.memory_condition,
                     "base_score": base.task_score,
                     "treated_score": treated.task_score,
                     "cell": cell})
    return {"rows": rows,
            "counts": {c: sum(1 for r in rows if r["cell"] == c)
                       for c in ("memory-not-shown-necessary",
                                 "beneficial-memory-contribution",
                                 "harmful-memory-contribution",
                                 "memory-failed-to-repair")}}
