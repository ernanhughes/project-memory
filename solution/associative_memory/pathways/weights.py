"""Association strengths as a versioned overlay on a base graph.

If association strengths can change, the graph is no longer merely
rebuildable derived state: it carries history that a rebuild would
destroy. The design that keeps rebuild possible is an append-only update
log over an immutable base.

    association state = base graph + ordered update log

Nothing mutates the base. Replaying the log reproduces the current
weights exactly, truncating the log rolls back to any earlier point, and
the question "why is this pathway strong?" has a literal answer: the
list of updates that made it so, each with its reason and the outcome it
came from.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AssociationUpdate:
    """One recorded change to one edge's retrieval priority."""

    edge_id: str
    prior_weight: float
    new_weight: float
    reason: str
    outcome: str
    cue: str = ""
    policy_version: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AssociationState:
    """Base weights plus the log that transformed them."""

    base_graph_version: str
    policy_version: str
    base_weights: dict[str, float] = field(default_factory=dict)
    updates: list[AssociationUpdate] = field(default_factory=list)

    # -- replay ---------------------------------------------------------

    def current_weights(self) -> dict[str, float]:
        weights = dict(self.base_weights)
        for update in self.updates:
            weights[update.edge_id] = update.new_weight
        return weights

    def weights_at(self, index: int) -> dict[str, float]:
        """Weights after the first ``index`` updates. Rollback and replay."""
        weights = dict(self.base_weights)
        for update in self.updates[:index]:
            weights[update.edge_id] = update.new_weight
        return weights

    def history_for(self, edge_id: str) -> list[AssociationUpdate]:
        return [update for update in self.updates if update.edge_id == edge_id]

    def explain(self, edge_id: str) -> str:
        history = self.history_for(edge_id)
        base = self.base_weights.get(edge_id, 0.0)
        lines = [f"{edge_id}: base association {base:.3f}"]
        if not history:
            lines.append("  never updated")
            return "\n".join(lines)
        for update in history:
            lines.append(
                f"  {update.timestamp} {update.prior_weight:.3f} -> "
                f"{update.new_weight:.3f}  ({update.reason}; outcome="
                f"{update.outcome}; cue={update.cue!r})"
            )
        return "\n".join(lines)

    def record(self, update: AssociationUpdate) -> None:
        if not update.timestamp:
            update.timestamp = datetime.now(timezone.utc).isoformat()
        update.policy_version = update.policy_version or self.policy_version
        self.updates.append(update)

    # -- application -----------------------------------------------------

    def apply_to(self, graph) -> None:
        """Write current weights onto a graph's edges in place.

        The graph passed here should be a working copy. The base weights
        remain recoverable from this object.
        """
        weights = self.current_weights()
        for edge in graph.edges:
            if edge.edge_id in weights:
                edge.association = weights[edge.edge_id]

    # -- persistence ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "base_graph_version": self.base_graph_version,
            "policy_version": self.policy_version,
            "base_weights": self.base_weights,
            "updates": [update.to_dict() for update in self.updates],
        }

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: Path) -> "AssociationState":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        state = cls(
            base_graph_version=payload["base_graph_version"],
            policy_version=payload["policy_version"],
            base_weights=dict(payload.get("base_weights", {})),
        )
        state.updates = [
            AssociationUpdate(**item) for item in payload.get("updates", [])
        ]
        return state

    @classmethod
    def from_graph(cls, graph, policy_version: str) -> "AssociationState":
        return cls(
            base_graph_version=graph.version,
            policy_version=policy_version,
            base_weights={edge.edge_id: edge.association for edge in graph.edges},
        )
