"""Activation decay: why remembering does not reach everything.

Three different decays are easy to confuse, and the book keeps them apart:

1. **Activation decay** — weakening during one traversal, as distance
   from the cue grows. That is this module.
2. **Association decay** — a pathway becoming less preferred over long
   periods of disuse. That is ``pathways.learning``, and it is Stage B.
3. **Forgetting** — a policy about what should cease to influence
   behaviour at all. That is not this chapter's problem.

The engineering reason for (1) is blunt: without it, almost the whole
connected component eventually counts as relevant, and precision — the
residual weakness the Chapter 3 runs already show — collapses further.
"""

from __future__ import annotations

import math


def hop_decay(value: float, hop: int, rate: float) -> float:
    """Geometric attenuation with distance from the cue."""
    return value * (rate ** max(0, hop))


def exponential_time_decay(
    weight: float, gap_days: float, rate: float = 0.01
) -> float:
    """Weaken an edge in proportion to the time it spans.

    Used only where an edge carries a temporal gap (sequence edges).
    Recency is an accessibility preference, not a claim that the recent
    thing is true; temporal validity belongs to Chapter 8.
    """
    return weight * math.exp(-rate * max(0.0, gap_days))


def normalise(levels: dict[str, float]) -> dict[str, float]:
    """Rescale so the largest activation is 1.0.

    Normalisation keeps thresholds comparable across cues that seed with
    different total mass. It changes no ordering.
    """
    if not levels:
        return {}
    peak = max(levels.values())
    if peak <= 0.0:
        return {key: 0.0 for key in levels}
    return {key: value / peak for key, value in levels.items()}


def apply_threshold(levels: dict[str, float], threshold: float) -> dict[str, float]:
    """Drop activation below the floor. The frontier stops growing here."""
    return {key: value for key, value in levels.items() if value >= threshold}
