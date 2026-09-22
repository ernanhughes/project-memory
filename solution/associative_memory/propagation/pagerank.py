"""Personalized PageRank over the memory graph.

The mechanism modern graph-memory systems reach for. The query does not
change the graph; it changes the *reset distribution* — the place the
random walk keeps restarting from — which is exactly the seed-activation
interface this package already has.

Two properties matter for the book's argument. PPR is a stationary
distribution, so it has no notion of hop count: it can tell you that a
memory is reachable and important, but not that it was three steps away.
Path length is therefore recovered separately, from the best-parent
trail, and the value it reports is approximate for this strategy. That
cost is real, and it is why bounded spreading activation is implemented
alongside rather than replaced by PPR.
"""

from __future__ import annotations

import time

from ..activation.decay import apply_threshold, normalise
from ..activation.state import ActivationState
from ..seeding.base import Seed
from .base import RetrievalResult
from .select import build_memories


class PersonalizedPageRankRetriever:
    """Power iteration with a seed-weighted reset vector."""

    name = "pagerank"

    def __init__(self, propagation, selection, edge_weight=None) -> None:
        self.propagation = propagation
        self.selection = selection
        self.edge_weight = edge_weight or (lambda cue, edge: edge.association)

    def retrieve(self, cue: str, graph, seeds: list[Seed]) -> RetrievalResult:
        started = time.perf_counter()
        config = self.propagation
        node_ids = graph.node_ids()
        index = {node_id: position for position, node_id in enumerate(node_ids)}
        size = len(node_ids)
        state = ActivationState()
        if size == 0 or not seeds:
            state.terminated_because = "no-seeds"
            return RetrievalResult(
                cue=cue, strategy=self.name, seeds=list(seeds), state=state,
                terminated_because="no-seeds",
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )

        seed_mass = sum(max(0.0, seed.score) for seed in seeds) or 1.0
        reset = [0.0] * size
        for seed in seeds:
            if seed.node_id in index:
                reset[index[seed.node_id]] += max(0.0, seed.score) / seed_mass
            state.seed(seed.node_id, seed.score)

        # Row-normalised transition weights, built once per query because
        # the weights may be cue-conditioned.
        outgoing: list[list[tuple[int, float, object]]] = [[] for _ in range(size)]
        edges_traversed = 0
        for node_id in node_ids:
            position = index[node_id]
            neighbours = graph.neighbours(node_id)
            weights = []
            for neighbour, edge in neighbours:
                weight = max(0.0, self.edge_weight(cue, edge))
                weights.append((index[neighbour], weight, edge))
                edges_traversed += 1
            total = sum(weight for _, weight, _ in weights)
            if total <= 0.0:
                continue
            outgoing[position] = [
                (target, weight / total, edge) for target, weight, edge in weights
            ]

        scores = list(reset)
        iterations = 0
        for iterations in range(1, config.pagerank_iterations + 1):
            updated = [(1.0 - config.damping) * value for value in reset]
            for position, targets in enumerate(outgoing):
                mass = scores[position]
                if mass <= 0.0:
                    continue
                for target, weight, _edge in targets:
                    updated[target] += config.damping * mass * weight
            delta = sum(abs(a - b) for a, b in zip(updated, scores))
            scores = updated
            if delta < config.pagerank_tolerance:
                break

        # Recover a best-parent trail so the result can still answer
        # "why did this memory become active?". Approximate by construction.
        for position, targets in enumerate(outgoing):
            mass = scores[position]
            if mass <= 0.0:
                continue
            for target, weight, edge in targets:
                state.deliver(
                    step=1,
                    source=node_ids[position],
                    target=node_ids[target],
                    edge_id=edge.edge_id,
                    relation=edge.relation,
                    amount=mass * weight,
                    edge_weight=weight,
                )

        state.levels = {
            node_ids[position]: score
            for position, score in enumerate(scores)
            if score > 0.0
        }
        state.levels = normalise(
            apply_threshold(state.levels, config.activation_threshold)
        )
        for seed in seeds:
            state.levels.setdefault(seed.node_id, seed.score)
        state.nodes_expanded = len(state.levels)
        state.steps_run = iterations
        state.terminated_because = (
            "converged" if iterations < config.pagerank_iterations
            else "iteration-budget"
        )
        admitted, explored = build_memories(graph, state, seeds, self.selection)
        return RetrievalResult(
            cue=cue,
            strategy=self.name,
            seeds=list(seeds),
            admitted=admitted,
            explored=explored,
            state=state,
            nodes_expanded=state.nodes_expanded,
            edges_traversed=edges_traversed,
            steps_run=iterations,
            terminated_because=state.terminated_because,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            notes="hop counts are approximate under a stationary distribution",
        )
