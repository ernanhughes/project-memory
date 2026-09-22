"""Query routing: different questions traverse memory differently (§18).

This is a rule-based starting point, not a learned router. The routing
experiment compares fixed single-method conditions against this simple
class-based routing to test whether question class predicts the useful
traversal — a result that could later earn a policy mechanism.
"""

from __future__ import annotations

# Task family → GraphRAG method. Rationale per class:
# - locate: answer concentrated in one/few regions → basic (vector analogue).
# - decision/provenance/temporal/use: entity-centred questions → local.
# - relational: traversal among entities/artifacts → local.
# - global: corpus-wide synthesis → global.
ROUTING_TABLE = {
    "locate": "basic",
    "decision": "local",
    "provenance": "local",
    "temporal": "local",
    "open-loop": "local",
    "use": "local",
    "relational": "local",
    "global": "global",
}

CONDITIONS = ("basic", "local", "global", "drift", "routed")


def route(task_family: str) -> str:
    """Return the GraphRAG method for a task family (default: local)."""
    return ROUTING_TABLE.get(task_family, "local")


def describe_routing() -> dict:
    return {
        "policy": "rule-based task-family routing (no learning)",
        "table": dict(ROUTING_TABLE),
    }


def route_question(question: str) -> str:
    """Query-only experimental router; never reads benchmark family labels."""
    text = question.lower()
    if any(term in text for term in ("across the", "major themes", "overall", "whole project")):
        return "global"
    if any(term in text for term in ("which file", "find the", "where was")):
        return "basic"
    return "local"
