"""Associative retrieval over a persistent memory graph (book Chapter 5).

Chapter 3 retrieves passages that resemble the query. Chapter 4 persists
derived structure — entities, relationships, claims, communities — with
provenance back to the source artifacts. This package asks the next
question: once memories have persistent representations and
relationships, how should activation move through them so that one
remembered thing can lead to another?

    cue
     ↓  seeding          (lexical | embedding | hybrid | oracle)
    seed activation
     ↓  propagation      (direct | pagerank | spreading | conditioned)
    activated subgraph
     ↓  decay, competition, budget
    selected memories + retrieval trace
     ↓
    context

Four invariants hold throughout, and the code is arranged so that
breaking one is visible rather than convenient:

* raw source artifacts remain authoritative; nothing here rewrites them;
* derived graph state remains rebuildable, and adaptive weights are an
  append-only overlay that can be replayed or rolled back;
* association strength is retrieval priority, never epistemic confidence;
* traversal is inspectable — every admitted memory carries the route
  that activated it, which explains retrieval causality and not truth.
"""

from .config import (  # noqa: F401
    AssociativeConfig,
    LearningConfig,
    PropagationConfig,
    SeedConfig,
    SelectionConfig,
)
from .pipeline import AssociativeMemory, build_retriever  # noqa: F401

__all__ = [
    "AssociativeConfig",
    "AssociativeMemory",
    "LearningConfig",
    "PropagationConfig",
    "SeedConfig",
    "SelectionConfig",
    "build_retriever",
]
