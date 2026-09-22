"""Activation: the per-query quantity that never touches stored state.

A node's activation says how strongly the current cue lights it up. It is
not a property of the memory, it is a property of this act of
remembering. Nothing in this module writes to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ActivationEvent:
    """One transfer of activation, recorded so a path can be reconstructed."""

    step: int
    source: str
    target: str
    edge_id: str
    relation: str
    delivered: float
    edge_weight: float
    note: str = ""


@dataclass
class ActivationState:
    """Activation levels plus the audit trail that explains them."""

    levels: dict[str, float] = field(default_factory=dict)
    # For each node, the (predecessor, edge_id, step) that delivered its
    # largest single contribution. This is what makes "why did this
    # memory become active?" answerable.
    best_parent: dict[str, tuple[str, str, int]] = field(default_factory=dict)
    hops: dict[str, int] = field(default_factory=dict)
    events: list[ActivationEvent] = field(default_factory=list)
    seeds: dict[str, float] = field(default_factory=dict)
    suppressed: dict[str, float] = field(default_factory=dict)
    nodes_expanded: int = 0
    steps_run: int = 0
    terminated_because: str = ""

    # -- seeding --------------------------------------------------------

    def seed(self, node_id: str, value: float) -> None:
        self.levels[node_id] = max(self.levels.get(node_id, 0.0), value)
        self.seeds[node_id] = self.levels[node_id]
        self.hops.setdefault(node_id, 0)

    # -- transfers --------------------------------------------------------

    def deliver(
        self,
        step: int,
        source: str,
        target: str,
        edge_id: str,
        relation: str,
        amount: float,
        edge_weight: float,
    ) -> None:
        if amount <= 0.0:
            return
        previous_best = 0.0
        if target in self.best_parent:
            parent_event = next(
                (
                    event
                    for event in reversed(self.events)
                    if event.target == target
                    and event.source == self.best_parent[target][0]
                    and event.edge_id == self.best_parent[target][1]
                ),
                None,
            )
            previous_best = parent_event.delivered if parent_event else 0.0
        self.levels[target] = self.levels.get(target, 0.0) + amount
        self.events.append(
            ActivationEvent(
                step=step,
                source=source,
                target=target,
                edge_id=edge_id,
                relation=relation,
                delivered=amount,
                edge_weight=edge_weight,
            )
        )
        if amount > previous_best:
            self.best_parent[target] = (source, edge_id, step)
        proposed = self.hops.get(source, 0) + 1
        if target not in self.hops or proposed < self.hops[target]:
            self.hops[target] = proposed

    def suppress(self, node_id: str, retained: float) -> None:
        """Record inhibition rather than silently deleting activation."""
        self.suppressed[node_id] = self.levels.get(node_id, 0.0) - retained
        self.levels[node_id] = retained

    # -- readout ----------------------------------------------------------

    def active(self, threshold: float = 0.0) -> list[tuple[str, float]]:
        return sorted(
            (
                (node_id, level)
                for node_id, level in self.levels.items()
                if level > threshold
            ),
            key=lambda item: (-item[1], item[0]),
        )

    def total_activation(self) -> float:
        return sum(self.levels.values())

    def concentration(self, top: int = 5) -> float:
        """Share of all activation held by the strongest few nodes.

        Near 1.0 means recall settled on a coherent region; near 0 means
        it smeared across the graph. Diagnostic, not a score.
        """
        total = self.total_activation()
        if total <= 0.0:
            return 0.0
        head = sum(level for _, level in self.active()[:top])
        return head / total

    def path_to(self, node_id: str, limit: int = 12) -> list[str]:
        """Reconstruct the strongest route from a seed to ``node_id``."""
        path = [node_id]
        seen = {node_id}
        current = node_id
        while current not in self.seeds and len(path) < limit:
            parent = self.best_parent.get(current)
            if parent is None or parent[0] in seen:
                break
            current = parent[0]
            seen.add(current)
            path.append(current)
        return list(reversed(path))
