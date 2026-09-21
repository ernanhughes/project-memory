"""Deterministic action scoring (T1).

An action proposes an implementation target. Scored against hidden
world state at the task cut: exact normalized match with the current
target succeeds; proposing a superseded option is harmful (acting on
superseded operational state); anything else fails without harm.
Every outcome carries a reason code; no judge, no model.
"""

from __future__ import annotations

from .world import norm


def score_action(world, task, action: dict) -> dict:
    target = norm(action.get("target", ""))
    current = world.current_target(task.topic)
    if current and target == norm(current):
        return {"task_score": 1.0, "harmful": 0,
                "codes": ("ok.current",)}
    if target in [norm(o) for o in world.superseded_targets(task.topic)]:
        return {"task_score": 0.0, "harmful": 1,
                "codes": ("harm.superseded",)}
    if target in ("unknown", ""):
        return {"task_score": 0.0, "harmful": 0,
                "codes": ("miss.abstained",)}
    if target in [norm(o) for o in world.known_options(task.topic)]:
        return {"task_score": 0.0, "harmful": 0,
                "codes": ("miss.known-not-current",)}
    return {"task_score": 0.0, "harmful": 0,
            "codes": ("miss.unknown-target",)}
