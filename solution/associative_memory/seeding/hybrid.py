"""Hybrid and oracle seeding.

``HybridSeeder`` blends lexical and embedding scores. ``OracleSeeder``
reads the ledger's expected evidence directly; it is not a deployable
system, it is the diagnostic that separates a seeding failure from a
propagation failure. When oracle seeding fixes a case that hybrid
seeding fails, the fault is in the entrance to the graph, not in the
journey through it.
"""

from __future__ import annotations

from .base import Seed, top_seeds
from .embedding import EmbeddingSeeder
from .lexical import LexicalSeeder


class HybridSeeder:
    """Weighted sum of normalised lexical and embedding scores."""

    name = "hybrid"

    def __init__(
        self,
        lexical: LexicalSeeder | None = None,
        embedding: EmbeddingSeeder | None = None,
        lexical_weight: float = 0.5,
        top_k: int = 5,
        min_score: float = 0.05,
    ) -> None:
        pool = max(top_k * 4, 20)
        self.lexical = lexical or LexicalSeeder(top_k=pool, min_score=0.0)
        self.embedding = embedding or EmbeddingSeeder(top_k=pool, min_score=0.0)
        self.lexical_weight = lexical_weight
        self.top_k = top_k
        self.min_score = min_score

    @staticmethod
    def _normalised(seeds: list[Seed]) -> dict[str, tuple[float, tuple[str, ...]]]:
        if not seeds:
            return {}
        peak = max(seed.score for seed in seeds) or 1.0
        return {
            seed.node_id: (seed.score / peak, seed.evidence) for seed in seeds
        }

    def seed(self, cue: str, graph) -> list[Seed]:
        lexical = self._normalised(self.lexical.seed(cue, graph))
        dense = self._normalised(self.embedding.seed(cue, graph))
        combined: dict[str, tuple[float, tuple[str, ...]]] = {}
        for node_id in set(lexical) | set(dense):
            lex_score, lex_evidence = lexical.get(node_id, (0.0, ()))
            emb_score, emb_evidence = dense.get(node_id, (0.0, ()))
            score = (
                self.lexical_weight * lex_score
                + (1.0 - self.lexical_weight) * emb_score
            )
            combined[node_id] = (
                score,
                tuple(
                    [f"lexical={lex_score:.3f}", f"embedding={emb_score:.3f}"]
                    + list(lex_evidence)
                    + list(emb_evidence)
                ),
            )
        return top_seeds(combined, self.name, self.top_k, self.min_score)


class OracleSeeder:
    """Seed exactly the nodes the ledger says the case needs. Upper bound."""

    name = "oracle"

    def __init__(self, expected_nodes: dict[str, list[str]]) -> None:
        self.expected_nodes = expected_nodes

    def seed(self, cue: str, graph) -> list[Seed]:
        wanted = self.expected_nodes.get(cue, [])
        return [
            Seed(node_id=node_id, score=1.0, method=self.name,
                 evidence=("ledger-supplied",))
            for node_id in wanted
            if node_id in graph.nodes
        ]


def build_seeder(config, oracle_nodes: dict[str, list[str]] | None = None):
    """Construct the seeder named by a ``SeedConfig``."""
    method = config.method
    if method == "lexical":
        return LexicalSeeder(top_k=config.top_k, min_score=config.min_score)
    if method == "embedding":
        from memory_baseline.embeddings import (
            HashingEmbedder,
            OllamaEmbeddingProvider,
        )

        provider = (
            HashingEmbedder(config.embedding_dimension)
            if config.embedding_provider == "hashing"
            else OllamaEmbeddingProvider(config.embedding_model)
        )
        return EmbeddingSeeder(
            provider=provider, top_k=config.top_k, min_score=config.min_score
        )
    if method == "hybrid":
        return HybridSeeder(
            lexical_weight=config.lexical_weight,
            top_k=config.top_k,
            min_score=config.min_score,
        )
    if method == "oracle":
        return OracleSeeder(oracle_nodes or {})
    raise ValueError(f"unknown seeding method: {method}")
