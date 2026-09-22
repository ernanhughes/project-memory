"""Embedding seeding: cue vector against node description vectors.

Reuses the Chapter 3 embedding providers rather than introducing a second
embedding stack, so a run's embedding identity means the same thing in
both chapters. The deterministic demo uses ``HashingEmbedder``, which
preserves no semantics and must never appear in a reported comparison —
it exists so the fixture experiments run without a model server, and runs
that use it are labelled as such in the manifest.
"""

from __future__ import annotations

import sys
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))

from memory_baseline.embeddings import (  # noqa: E402
    EmbeddingProvider,
    HashingEmbedder,
    cosine,
)

from .base import Seed, node_text, top_seeds  # noqa: E402


class EmbeddingSeeder:
    """Cosine similarity between the cue and each node's text."""

    name = "embedding"

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        top_k: int = 5,
        min_score: float = 0.05,
    ) -> None:
        self.provider = provider or HashingEmbedder(256)
        self.top_k = top_k
        self.min_score = min_score
        self._vectors: dict[int, dict[str, list[float]]] = {}

    def _node_vectors(self, graph) -> dict[str, list[float]]:
        key = id(graph)
        cached = self._vectors.get(key)
        if cached is not None:
            return cached
        node_ids = graph.node_ids()
        texts = [node_text(graph.nodes[node_id]) for node_id in node_ids]
        result = self.provider.embed(texts)
        vectors = dict(zip(node_ids, result.vectors))
        self._vectors[key] = vectors
        return vectors

    def seed(self, cue: str, graph) -> list[Seed]:
        vectors = self._node_vectors(graph)
        cue_vector = self.provider.embed([cue]).vectors[0]
        scored: dict[str, tuple[float, tuple[str, ...]]] = {}
        for node_id, vector in vectors.items():
            score = cosine(cue_vector, vector)
            if score <= 0.0:
                continue
            scored[node_id] = (score, (f"cosine={score:.3f}",))
        return top_seeds(scored, self.name, self.top_k, self.min_score)

    def version(self) -> str:
        return self.provider.version()
