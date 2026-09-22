"""Competition between pathways.

An entity that appears in a hundred relationships should not hand a
hundredth of its meaning to every neighbour equally. Two mechanisms do
the work, both borrowed from cognitive models and both implemented here
as arithmetic rather than as metaphor:

**Fan division.** Outgoing activation is divided by the sender's degree,
so a hub transmits weakly per edge. The fan effect is a human latency
result; using it as a ranking penalty is an engineering analogy and is
labelled as one.

**Lateral inhibition.** Only the strongest few nodes on a frontier keep
full activation; the rest are damped. This is what stops four plausible
pathways out of one entity from each claiming a quarter of the context
budget. It is also the mechanism most likely to cause the failure the
SYNAPSE authors call cognitive tunnelling, where inhibition buries a
correct but quiet memory under a loud hub — so it is measured, not
assumed.
"""

from __future__ import annotations


def fan_divisor(degree: int, enabled: bool) -> float:
    """Denominator applied to a node's outgoing activation."""
    if not enabled:
        return 1.0
    return float(max(1, degree))


def lateral_inhibition(
    frontier: dict[str, float],
    top_m: int,
    strength: float,
) -> tuple[dict[str, float], dict[str, float]]:
    """Keep the strongest ``top_m``; damp the rest by ``strength``.

    Returns ``(kept, suppressed_amounts)``. Suppression is returned
    rather than discarded so the trace can report what competition
    removed — an inhibited memory that turns out to have been the right
    one is a diagnosable failure, not an invisible one.
    """
    if not frontier or top_m <= 0 or strength <= 0.0:
        return dict(frontier), {}
    ranked = sorted(frontier.items(), key=lambda item: (-item[1], item[0]))
    kept: dict[str, float] = {}
    suppressed: dict[str, float] = {}
    for index, (node_id, level) in enumerate(ranked):
        if index < top_m:
            kept[node_id] = level
        else:
            retained = level * (1.0 - min(1.0, strength))
            kept[node_id] = retained
            suppressed[node_id] = level - retained
    return kept, suppressed


def competition_report(
    frontier: dict[str, float], top_m: int
) -> dict[str, float]:
    """How concentrated a frontier is before inhibition acts.

    Reported so that a chapter claim about competition can be checked
    against the case where competition had nothing to do.
    """
    if not frontier:
        return {"frontier_size": 0.0, "head_share": 0.0}
    total = sum(frontier.values())
    ranked = sorted(frontier.values(), reverse=True)
    head = sum(ranked[: max(1, top_m)])
    return {
        "frontier_size": float(len(frontier)),
        "head_share": (head / total) if total > 0 else 0.0,
    }
