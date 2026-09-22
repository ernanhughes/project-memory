"""Cue-conditioned propagation.

The mechanism that makes the chapter's central claim testable. Without
it, an entity's neighbourhood is fixed: whatever the cue, activation
leaves that node the same way. With it, the edge weight is recomputed per
cue from the agreement between the cue and the edge's own description, so
two cues naming the same actor travel different routes.

This is the mechanism MemORAI calls dynamic weighted PageRank. Their own
ablation puts it at a small positive contribution next to scoping and
segmentation, which is recorded here so the chapter does not oversell it
before measuring it.

The conditioning is deliberately transparent: a weight multiplier derived
from term overlap between the cue and the edge, floored so that a
cue-irrelevant edge is attenuated rather than severed. Severing edges
would make the graph itself query-dependent, which would break the
separation between what the graph asserts and what this retrieval
prefers.
"""

from __future__ import annotations

from ..seeding.base import tokenise
from .pagerank import PersonalizedPageRankRetriever
from .spreading import SpreadingActivationRetriever


class CueConditionedWeights:
    """Multiplier on association strength from cue/edge agreement."""

    def __init__(self, strength: float = 1.0, floor: float = 0.1) -> None:
        self.strength = strength
        self.floor = floor
        self._cue_cache: dict[str, set[str]] = {}
        self._edge_cache: dict[str, set[str]] = {}

    def _cue_tokens(self, cue: str) -> set[str]:
        cached = self._cue_cache.get(cue)
        if cached is None:
            cached = set(tokenise(cue))
            self._cue_cache[cue] = cached
        return cached

    def _edge_tokens(self, edge) -> set[str]:
        cached = self._edge_cache.get(edge.edge_id)
        if cached is None:
            text = " ".join(
                part
                for part in (edge.relation, edge.description, *edge.source_ids)
                if part
            )
            cached = set(tokenise(text))
            self._edge_cache[edge.edge_id] = cached
        return cached

    def __call__(self, cue: str, edge) -> float:
        base = edge.association
        if self.strength <= 0.0:
            return base
        cue_tokens = self._cue_tokens(cue)
        edge_tokens = self._edge_tokens(edge)
        if not cue_tokens or not edge_tokens:
            return base * self.floor if self.strength >= 1.0 else base
        overlap = len(cue_tokens & edge_tokens) / len(cue_tokens)
        multiplier = self.floor + (1.0 - self.floor) * min(1.0, overlap * 2.0)
        blended = (1.0 - self.strength) * 1.0 + self.strength * multiplier
        return base * blended


class CueConditionedRetriever(SpreadingActivationRetriever):
    """Spreading activation whose edge weights depend on the active cue."""

    name = "conditioned"

    def __init__(self, propagation, selection) -> None:
        super().__init__(
            propagation,
            selection,
            edge_weight=CueConditionedWeights(
                strength=propagation.conditioning_strength,
                floor=propagation.conditioning_floor,
            ),
        )


class CueConditionedPageRankRetriever(PersonalizedPageRankRetriever):
    """Personalized PageRank with cue-conditioned edge weights."""

    name = "conditioned-pagerank"

    def __init__(self, propagation, selection) -> None:
        super().__init__(
            propagation,
            selection,
            edge_weight=CueConditionedWeights(
                strength=propagation.conditioning_strength,
                floor=propagation.conditioning_floor,
            ),
        )
