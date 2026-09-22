"""Wiring: cue in, bounded selection of memories and a trace out.

The pipeline is deliberately thin. It owns no policy of its own; it
chooses a seeder and a retriever from configuration, runs them, and hands
back a result. Every interesting decision lives in a module that can be
swapped, ablated, or turned off from the config, because the chapter's
job is to find out which of them are worth having.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import AssociativeConfig
from .graph.adapter import MemoryGraph
from .pathways.trace import build_trace, explain
from .pathways.weights import AssociationState
from .propagation.base import RetrievalResult
from .propagation.conditioned import (
    CueConditionedPageRankRetriever,
    CueConditionedRetriever,
)
from .propagation.direct import DirectNeighbourhoodRetriever
from .propagation.pagerank import PersonalizedPageRankRetriever
from .propagation.spreading import SpreadingActivationRetriever
from .seeding.hybrid import build_seeder

STRATEGIES = (
    "direct",
    "pagerank",
    "spreading",
    "conditioned",
    "conditioned-pagerank",
)


def build_retriever(config: AssociativeConfig, strategy: str | None = None):
    """Construct the retriever named by configuration."""
    name = strategy or config.propagation.strategy
    propagation, selection = config.propagation, config.selection
    if name == "direct":
        return DirectNeighbourhoodRetriever(propagation, selection)
    if name == "pagerank":
        return PersonalizedPageRankRetriever(propagation, selection)
    if name == "spreading":
        return SpreadingActivationRetriever(propagation, selection)
    if name == "conditioned":
        return CueConditionedRetriever(propagation, selection)
    if name == "conditioned-pagerank":
        return CueConditionedPageRankRetriever(propagation, selection)
    raise ValueError(f"unknown propagation strategy: {name}")


@dataclass
class AssociativeMemory:
    """One configured associative-retrieval system over one graph."""

    graph: MemoryGraph
    config: AssociativeConfig
    strategy: str | None = None
    oracle_nodes: dict[str, list[str]] | None = None
    association_state: AssociationState | None = None

    def __post_init__(self) -> None:
        self.seeder = build_seeder(self.config.seeding, self.oracle_nodes)
        self.retriever = build_retriever(self.config, self.strategy)
        if self.association_state is not None:
            self.association_state.apply_to(self.graph)

    @classmethod
    def from_paths(
        cls,
        graph_path: str | Path,
        config: AssociativeConfig | None = None,
        strategy: str | None = None,
        oracle_nodes: dict[str, list[str]] | None = None,
    ) -> "AssociativeMemory":
        config = config or AssociativeConfig()
        return cls(
            graph=MemoryGraph.load(Path(graph_path)),
            config=config,
            strategy=strategy,
            oracle_nodes=oracle_nodes,
        )

    # -- retrieval --------------------------------------------------------

    def retrieve(self, cue: str) -> RetrievalResult:
        seeds = self.seeder.seed(cue, self.graph)
        return self.retriever.retrieve(cue, self.graph, seeds)

    def traces(self, result: RetrievalResult, limit: int = 5):
        return [
            build_trace(self.graph, result.state, memory)
            for memory in result.admitted[:limit]
        ]

    def explain(self, result: RetrievalResult, limit: int = 5) -> str:
        return explain(self.graph, result, limit=limit)

    # -- manifest ----------------------------------------------------------

    def manifest(self) -> dict:
        record = {
            "graph_version": self.graph.version,
            "corpus_version": self.graph.corpus_version,
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
            "seeder": self.seeder.name,
            "strategy": self.retriever.name,
            "config": self.config.to_dict(),
        }
        if self.association_state is not None:
            record["association_policy_version"] = (
                self.association_state.policy_version
            )
            record["association_updates"] = len(self.association_state.updates)
            record["base_graph_version"] = (
                self.association_state.base_graph_version
            )
        return record
