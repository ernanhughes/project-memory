"""Candidate generation: the Chapter 3 baseline, kept intact.

Chapter 10 does not replace retrieval. It runs above it. The retriever
here is the Chapter 3 shape -- lexical search, dense search, reciprocal
rank fusion -- reimplemented over an in-process corpus so the suite runs
without PostgreSQL while keeping the same ranking semantics:

* lexical: Okapi BM25 with OR-of-terms semantics, matching the reason
  Chapter 3 rejected plain AND matching for question phrasing;
* dense: cosine over embeddings from the book's embedding model
  (``bge-m3`` via Ollama), cached to disk so a frozen run replays;
* fusion: the same parameter-free RRF, k=60.

``HashingEmbedder`` from Chapter 3 is a test double and is never used in
a reported run. When no embedding service is reachable the retriever
degrades to lexical-only and says so in ``describe()``, so a run that
lacks dense retrieval can never be mistaken for one that had it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .model import MemoryUnit

FUSION_K = 60
DEFAULT_EMBED_MODEL = "bge-m3"
DEFAULT_OLLAMA = "http://localhost:11434"
CACHE_DIR = Path(__file__).resolve().parent / ".embed-cache"


def tokenise(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1]


# --------------------------------------------------------------------------
# Embeddings
# --------------------------------------------------------------------------

class OllamaEmbedder:
    """The book's embedding model, with an on-disk cache keyed by text."""

    def __init__(self, model: str = DEFAULT_EMBED_MODEL,
                 host: str = DEFAULT_OLLAMA,
                 cache_dir: Path = CACHE_DIR) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._mem: dict[str, list[float]] = {}

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def available(self) -> bool:
        try:
            urllib.request.urlopen(f"{self.host}/api/tags", timeout=3).read()
            return True
        except (urllib.error.URLError, OSError):
            return False

    def _key(self, text: str) -> str:
        digest = hashlib.sha256(f"{self.model}\x00{text}".encode()).hexdigest()
        return digest[:40]

    def embed_one(self, text: str) -> list[float]:
        key = self._key(text)
        if key in self._mem:
            return self._mem[key]
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            vector = json.loads(path.read_text())
            self._mem[key] = vector
            return vector
        payload = json.dumps({"model": self.model, "input": [text]}).encode()
        request = urllib.request.Request(
            f"{self.host}/api/embed", data=payload,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=300) as response:
            out = json.load(response)
        vector = [float(v) for v in out["embeddings"][0]]
        path.write_text(json.dumps(vector))
        self._mem[key] = vector
        return vector


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


# --------------------------------------------------------------------------
# BM25
# --------------------------------------------------------------------------

class BM25:
    """Okapi BM25 (k1=1.2, b=0.75) over the unit texts."""

    def __init__(self, units: list[MemoryUnit], k1: float = 1.2,
                 b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.ids = [u.unit_id for u in units]
        self.docs = [tokenise(u.text) for u in units]
        self.freqs = [Counter(d) for d in self.docs]
        self.lengths = [len(d) for d in self.docs]
        self.avgdl = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        self.df: Counter = Counter()
        for doc in self.docs:
            self.df.update(set(doc))
        self.n = len(self.docs)

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        terms = tokenise(query)
        if not terms:
            return []
        scored: list[tuple[str, float]] = []
        for i, freq in enumerate(self.freqs):
            score = 0.0
            for term in terms:
                tf = freq.get(term, 0)
                if not tf:
                    continue
                denom = tf + self.k1 * (
                    1 - self.b + self.b * self.lengths[i] / (self.avgdl or 1.0))
                score += self._idf(term) * tf * (self.k1 + 1) / denom
            if score > 0:
                scored.append((self.ids[i], score))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:k]


# --------------------------------------------------------------------------
# Hybrid retriever
# --------------------------------------------------------------------------

def reciprocal_rank_fusion(rankings: list[list[str]],
                           k: int = FUSION_K) -> list[tuple[str, float]]:
    """Chapter 3's fusion, unchanged: parameter-free, rank-based."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, unit_id in enumerate(ranking, start=1):
            scores[unit_id] = scores.get(unit_id, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores, key=lambda uid: (-scores[uid], uid))
    return [(uid, scores[uid]) for uid in ordered]


@dataclass
class RetrievalResult:
    ranked: list[tuple[str, float]]
    lexical: list[str]
    dense: list[str]
    mode: str


class HybridRetriever:
    def __init__(self, units: list[MemoryUnit],
                 embedder: OllamaEmbedder | None = None,
                 lexical_k: int = 60, dense_k: int = 60) -> None:
        self.units = {u.unit_id: u for u in units}
        self.order = [u.unit_id for u in units]
        self.bm25 = BM25(units)
        self.lexical_k = lexical_k
        self.dense_k = dense_k
        self.embedder = embedder
        self._vectors: dict[str, list[float]] = {}
        self.mode = "lexical"
        if embedder is not None and embedder.available():
            self.mode = "hybrid"

    def warm(self) -> None:
        """Embed the corpus once; cached vectors make replay exact."""
        if self.mode != "hybrid" or self._vectors:
            return
        for unit_id in self.order:
            self._vectors[unit_id] = self.embedder.embed_one(
                self.units[unit_id].text)

    def describe(self) -> str:
        if self.mode == "hybrid":
            return f"bm25+{self.embedder.name}+rrf{FUSION_K}"
        return f"bm25-only (no embedding service; rrf{FUSION_K} inactive)"

    def retrieve(self, query: str, k: int) -> RetrievalResult:
        lexical = [uid for uid, _ in self.bm25.search(query, self.lexical_k)]
        dense: list[str] = []
        if self.mode == "hybrid":
            self.warm()
            qvec = self.embedder.embed_one(query)
            scored = [(uid, cosine(qvec, vec))
                      for uid, vec in self._vectors.items()]
            scored.sort(key=lambda item: (-item[1], item[0]))
            dense = [uid for uid, _ in scored[:self.dense_k]]
            fused = reciprocal_rank_fusion([lexical, dense])
        else:
            fused = [(uid, 1.0 / (FUSION_K + rank))
                     for rank, uid in enumerate(lexical, start=1)]
        return RetrievalResult(ranked=fused[:k], lexical=lexical[:k],
                               dense=dense[:k], mode=self.mode)
