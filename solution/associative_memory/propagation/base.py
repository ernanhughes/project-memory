"""The associative-retrieval interface.

Four strategies implement it: bounded-hop neighbourhood, Personalized
PageRank, spreading activation, and cue-conditioned propagation. The
point of the interface is that no strategy is privileged — the chapter's
experiments decide which, if any, earns its cost, and a Type-B result
(the simplest one is already enough) must be expressible without
rewriting the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..activation.state import ActivationState
from ..seeding.base import Seed


@dataclass
class ActivatedMemory:
    """One memory the cue reached, with the route that reached it."""

    node_id: str
    label: str
    kind: str
    activation: float
    hops: int
    path: list[str] = field(default_factory=list)
    path_relations: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    score: float = 0.0
    seeded: bool = False

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "kind": self.kind,
            "activation": round(self.activation, 6),
            "score": round(self.score, 6),
            "hops": self.hops,
            "path": list(self.path),
            "path_relations": list(self.path_relations),
            "source_ids": list(self.source_ids),
            "seeded": self.seeded,
        }


@dataclass
class RetrievalResult:
    """What one act of associative retrieval produced.

    ``explored`` and ``admitted`` are reported separately on purpose.
    Associative search may explore broadly inside the graph; what it is
    allowed to hand to a reader is bounded, so the comparison against
    Chapters 3 and 4 cannot be won by enlarging the context.
    """

    cue: str
    strategy: str
    seeds: list[Seed] = field(default_factory=list)
    admitted: list[ActivatedMemory] = field(default_factory=list)
    explored: list[ActivatedMemory] = field(default_factory=list)
    state: ActivationState | None = None
    nodes_expanded: int = 0
    edges_traversed: int = 0
    steps_run: int = 0
    terminated_because: str = ""
    latency_ms: float = 0.0
    notes: str = ""

    def admitted_sources(self) -> list[str]:
        seen: list[str] = []
        for memory in self.admitted:
            for source_id in memory.source_ids:
                if source_id not in seen:
                    seen.append(source_id)
        return seen

    def explored_sources(self) -> list[str]:
        seen: list[str] = []
        for memory in self.explored:
            for source_id in memory.source_ids:
                if source_id not in seen:
                    seen.append(source_id)
        return seen

    def expansion_factor(self) -> float:
        """Memories activated per memory admitted."""
        if not self.admitted:
            return float(len(self.explored))
        return len(self.explored) / len(self.admitted)

    def to_dict(self) -> dict:
        return {
            "cue": self.cue,
            "strategy": self.strategy,
            "seeds": [seed.to_dict() for seed in self.seeds],
            "admitted": [memory.to_dict() for memory in self.admitted],
            "explored_count": len(self.explored),
            "nodes_expanded": self.nodes_expanded,
            "edges_traversed": self.edges_traversed,
            "steps_run": self.steps_run,
            "terminated_because": self.terminated_because,
            "expansion_factor": round(self.expansion_factor(), 4),
            "latency_ms": round(self.latency_ms, 3),
            "activation_concentration": (
                round(self.state.concentration(), 4) if self.state else None
            ),
            "notes": self.notes,
        }


class AssociativeRetriever(Protocol):
    """Propagate a cue through a memory graph under a fixed budget."""

    name: str

    def retrieve(self, cue: str, graph, seeds: list[Seed]) -> RetrievalResult:
        ...
