"""Turning activation into a bounded selection of memories.

Every strategy shares this step so that differences between strategies
are differences in propagation, not in how generously each one fills the
context. The final score fuses activation, direct cue similarity, and
structural importance with explicit weights — a deliberate echo of the
hybrid fusion SYNAPSE reports, kept visible rather than hidden inside a
learned ranker.
"""

from __future__ import annotations

from ..activation.state import ActivationState
from ..seeding.base import Seed
from .base import ActivatedMemory


def build_memories(
    graph,
    state: ActivationState,
    seeds: list[Seed],
    selection,
) -> tuple[list[ActivatedMemory], list[ActivatedMemory]]:
    """Return ``(admitted, explored)`` under the selection budget."""
    seed_scores = {seed.node_id: seed.score for seed in seeds}
    seed_ids = set(seed_scores)
    degrees = {node_id: graph.degree(node_id) for node_id in state.levels}
    max_degree = max(degrees.values()) if degrees else 1
    explored: list[ActivatedMemory] = []
    for node_id, level in state.active():
        node = graph.nodes.get(node_id)
        if node is None:
            continue
        path = state.path_to(node_id)
        importance = degrees.get(node_id, 0) / max(1, max_degree)
        score = (
            selection.activation_weight * level
            + selection.similarity_weight * seed_scores.get(node_id, 0.0)
            + selection.importance_weight * importance
        )
        explored.append(
            ActivatedMemory(
                node_id=node_id,
                label=node.label,
                kind=node.kind,
                activation=level,
                hops=state.hops.get(node_id, 0),
                path=path,
                path_relations=_relations_for(state, path),
                source_ids=list(node.source_ids),
                score=score,
                seeded=node_id in seed_ids,
            )
        )
    explored.sort(key=lambda memory: (-memory.score, memory.node_id))

    admitted: list[ActivatedMemory] = []
    sources: list[str] = []
    for memory in explored:
        if len(admitted) >= selection.max_memories:
            break
        new_sources = [s for s in memory.source_ids if s not in sources]
        if len(sources) + len(new_sources) > selection.max_sources and sources:
            continue
        admitted.append(memory)
        sources.extend(new_sources)
    return admitted, explored


def _relations_for(state: ActivationState, path: list[str]) -> list[str]:
    relations: list[str] = []
    for index in range(1, len(path)):
        parent = state.best_parent.get(path[index])
        if parent is None:
            relations.append("?")
            continue
        edge_id = parent[1]
        relation = next(
            (
                event.relation
                for event in state.events
                if event.edge_id == edge_id and event.target == path[index]
            ),
            "?",
        )
        relations.append(relation)
    return relations
