"""Bounded-hop neighbourhood expansion: the simplest graph baseline.

This is what a static graph memory already does — Microsoft GraphRAG's
local search is an entity neighbourhood plus its text. It is included
here so the chapter's headline comparison is honest: if one-hop
neighbourhood retrieval matches spreading activation, then propagation
has not earned anything, and the chapter shrinks accordingly.

Activation here is a pure function of distance: full at the seed,
attenuated by a fixed factor per hop, with no competition between
branches. That crudeness is the point.
"""

from __future__ import annotations

import time

from ..activation.state import ActivationState
from ..seeding.base import Seed
from .base import RetrievalResult
from .select import build_memories


class DirectNeighbourhoodRetriever:
    """Breadth-first expansion to ``max_hops`` with geometric hop decay."""

    name = "direct"

    def __init__(self, propagation, selection, hop_decay: float = 0.6) -> None:
        self.propagation = propagation
        self.selection = selection
        self.hop_decay = hop_decay

    def retrieve(self, cue: str, graph, seeds: list[Seed]) -> RetrievalResult:
        started = time.perf_counter()
        state = ActivationState()
        for seed in seeds:
            state.seed(seed.node_id, seed.score)
        frontier = [seed.node_id for seed in seeds]
        visited = set(frontier)
        edges_traversed = 0
        terminated = "frontier-exhausted"
        for hop in range(1, self.propagation.max_hops + 1):
            next_frontier: list[str] = []
            for node_id in frontier:
                for neighbour, edge in graph.neighbours(node_id):
                    edges_traversed += 1
                    delivered = (
                        state.levels.get(node_id, 0.0)
                        * self.hop_decay
                        * edge.association
                    )
                    if delivered < self.propagation.activation_threshold:
                        continue
                    state.deliver(
                        step=hop,
                        source=node_id,
                        target=neighbour,
                        edge_id=edge.edge_id,
                        relation=edge.relation,
                        amount=delivered,
                        edge_weight=edge.association,
                    )
                    if neighbour not in visited:
                        visited.add(neighbour)
                        next_frontier.append(neighbour)
                    if len(visited) >= self.propagation.max_nodes_expanded:
                        terminated = "node-budget"
                        break
                if terminated == "node-budget":
                    break
            state.steps_run = hop
            if terminated == "node-budget" or not next_frontier:
                break
            frontier = next_frontier
        else:
            terminated = "hop-budget"
        state.nodes_expanded = len(visited)
        state.terminated_because = terminated
        admitted, explored = build_memories(
            graph, state, seeds, self.selection
        )
        return RetrievalResult(
            cue=cue,
            strategy=self.name,
            seeds=list(seeds),
            admitted=admitted,
            explored=explored,
            state=state,
            nodes_expanded=len(visited),
            edges_traversed=edges_traversed,
            steps_run=state.steps_run,
            terminated_because=terminated,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
