"""Spreading activation with decay, fan division, and inhibition.

The mechanism Collins and Loftus described, implemented with the
constraints the information-retrieval literature found necessary before
the technique was usable at all: a bounded hop count, a node budget, an
activation threshold, division by fan, and competition on the frontier.

The update is the synchronous form SYNAPSE reports. At each step every
active node keeps a fraction of its own activation and receives what its
neighbours send:

    a_i(t+1) = retention · a_i(t)
               + Σ_j  spread · w_ji · a_j(t) / fan(j)

Written out as a sequence:

    retain a fraction of current activation
      ↓
    send along edges, weighted by association strength
      ↓
    divide by the sender's fan so hubs transmit weakly per edge
      ↓
    apply lateral inhibition to what arrives
      ↓
    drop everything under the threshold

Termination does not depend on a visited set. Activation decays
multiplicatively and the threshold cuts it off, so a cycle dies out
rather than circulating; the hop and node budgets are belt-and-braces,
and the tests check that each one can be the binding constraint.

Removing any constraint is a one-line configuration change, which is what
makes the per-component ablations in E5-D and E5-E cheap to run.
"""

from __future__ import annotations

import time

from ..activation.decay import apply_threshold, normalise
from ..activation.inhibition import fan_divisor, lateral_inhibition
from ..activation.state import ActivationState
from ..seeding.base import Seed
from .base import RetrievalResult
from .select import build_memories


class SpreadingActivationRetriever:
    """Iterative propagation under explicit constraints."""

    name = "spreading"

    def __init__(self, propagation, selection, edge_weight=None) -> None:
        self.propagation = propagation
        self.selection = selection
        # ``edge_weight(cue, edge)`` lets a subclass condition traversal
        # on the cue. The unconditioned version ignores the cue entirely.
        self.edge_weight = edge_weight or (lambda cue, edge: edge.association)

    def retrieve(self, cue: str, graph, seeds: list[Seed]) -> RetrievalResult:
        started = time.perf_counter()
        config = self.propagation
        state = ActivationState()
        for seed in seeds:
            state.seed(seed.node_id, seed.score)
        levels = dict(state.levels)
        touched = set(levels)
        edges_traversed = 0
        terminated = "activation-exhausted"
        steps = 0

        for step in range(1, config.max_hops + 1):
            steps = step
            incoming: dict[str, float] = {}
            for node_id, level in sorted(levels.items()):
                if level < config.activation_threshold:
                    continue
                neighbours = graph.neighbours(node_id)
                divisor = fan_divisor(len(neighbours), config.fan_division)
                for neighbour, edge in neighbours:
                    edges_traversed += 1
                    weight = self.edge_weight(cue, edge)
                    delivered = config.spread_factor * weight * level / divisor
                    if delivered < config.activation_threshold:
                        continue
                    incoming[neighbour] = incoming.get(neighbour, 0.0) + delivered
                    state.deliver(
                        step=step,
                        source=node_id,
                        target=neighbour,
                        edge_id=edge.edge_id,
                        relation=edge.relation,
                        amount=delivered,
                        edge_weight=weight,
                    )
            if not incoming:
                terminated = "activation-exhausted"
                break

            if config.inhibition:
                kept, suppressed = lateral_inhibition(
                    incoming, config.frontier_top_m, config.inhibition_strength
                )
                for node_id, lost in suppressed.items():
                    state.suppressed[node_id] = (
                        state.suppressed.get(node_id, 0.0) + lost
                    )
                incoming = kept

            updated = {
                node_id: level * config.retention
                for node_id, level in levels.items()
            }
            for node_id, delivered in incoming.items():
                updated[node_id] = updated.get(node_id, 0.0) + delivered
            levels = apply_threshold(updated, config.activation_threshold)
            touched.update(levels)

            if len(touched) >= config.max_nodes_expanded:
                terminated = "node-budget"
                break
            if step == config.max_hops:
                terminated = "hop-budget"

        state.levels = normalise(
            apply_threshold(levels, config.activation_threshold)
        )
        state.nodes_expanded = len(touched)
        state.steps_run = steps
        state.terminated_because = terminated
        admitted, explored = build_memories(graph, state, seeds, self.selection)
        return RetrievalResult(
            cue=cue,
            strategy=self.name,
            seeds=list(seeds),
            admitted=admitted,
            explored=explored,
            state=state,
            nodes_expanded=len(touched),
            edges_traversed=edges_traversed,
            steps_run=steps,
            terminated_because=terminated,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
