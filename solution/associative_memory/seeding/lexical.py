"""Lexical seeding: term overlap between cue and node text.

The cheapest credible seeder, and the one that handles the identifiers a
project history is full of (``adr-007``, ``incident-026``) better than
any embedding does. Its weakness is the obvious one: a cue phrased
without the corpus's vocabulary seeds nothing.
"""

from __future__ import annotations

import math
from collections import Counter

from .base import Seed, Seeder, node_text, tokenise, top_seeds


class LexicalSeeder:
    """Inverse-document-frequency weighted overlap, no external services."""

    name = "lexical"

    def __init__(self, top_k: int = 5, min_score: float = 0.05) -> None:
        self.top_k = top_k
        self.min_score = min_score
        self._idf_cache: dict[int, dict[str, float]] = {}

    def _idf(self, graph) -> dict[str, float]:
        key = id(graph)
        cached = self._idf_cache.get(key)
        if cached is not None:
            return cached
        counts: Counter[str] = Counter()
        total = max(1, len(graph.nodes))
        for node in graph.nodes.values():
            for token in set(tokenise(node_text(node))):
                counts[token] += 1
        idf = {
            token: math.log(1.0 + total / (1.0 + count))
            for token, count in counts.items()
        }
        self._idf_cache[key] = idf
        return idf

    def seed(self, cue: str, graph) -> list[Seed]:
        cue_tokens = set(tokenise(cue))
        if not cue_tokens:
            return []
        idf = self._idf(graph)
        cue_mass = sum(idf.get(token, 1.0) for token in cue_tokens) or 1.0
        scored: dict[str, tuple[float, tuple[str, ...]]] = {}
        for node_id, node in graph.nodes.items():
            tokens = set(tokenise(node_text(node)))
            shared = cue_tokens & tokens
            if not shared:
                continue
            weight = sum(idf.get(token, 1.0) for token in shared)
            scored[node_id] = (
                weight / cue_mass,
                tuple(sorted(shared)),
            )
        return top_seeds(scored, self.name, self.top_k, self.min_score)


def _assert_protocol() -> Seeder:
    return LexicalSeeder()
