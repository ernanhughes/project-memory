"""Stage B: can pathways learn? Off by default, and deliberately so.

The first chapter result must be interpretable without learned weights,
so nothing here runs unless ``LearningConfig.enabled`` is set. What the
module provides is a mechanism that can be turned on under controlled
conditions, plus the safeguards that the failure it invites demands.

The failure is specific. If retrieval frequency strengthened pathways,
then a wrong association that gets retrieved would be retrieved more,
and appear useful *because* it was retrieved. The ACL 2026 study of
experience-following gives the mechanism a name and evidence: agents
reproduce the outputs of similar retrieved records, so an error in stored
experience propagates into future behaviour and then into future stored
experience.

Four safeguards are therefore built in rather than recommended:

1. **Outcomes, not frequency.** Only a recorded task outcome moves a
   weight. Retrieval alone moves nothing.
2. **Evidence gates.** An edge with weak evidence confidence, or with no
   source provenance at all, is never strengthened however well the task
   went. A useful route through a fabricated relation stays weak.
3. **Bounds and decay.** Weights are clamped, and unused pathways decay,
   so no route can run away.
4. **Append-only records.** Every change is logged with its reason and
   the outcome that caused it, and can be replayed or rolled back.

Even with all four, this is an experimental mechanism whose safety is
E5-H's question, not this module's claim.
"""

from __future__ import annotations

from dataclasses import dataclass

from .weights import AssociationState, AssociationUpdate

GOOD = "useful"
BAD = "irrelevant"
HARMFUL = "harmful"
OUTCOMES = (GOOD, BAD, HARMFUL)


@dataclass
class OutcomeRecord:
    """What a downstream task reported about one retrieval."""

    cue: str
    outcome: str
    path_edges: tuple[str, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome: {self.outcome}")


class PathwayLearner:
    """Outcome-gated association updates with explicit refusals."""

    def __init__(self, config, state: AssociationState, graph) -> None:
        self.config = config
        self.state = state
        self.graph = graph
        self._edges = {edge.edge_id: edge for edge in graph.edges}
        self.refusals: list[tuple[str, str]] = []

    # -- gates -----------------------------------------------------------

    def _may_strengthen(self, edge_id: str) -> tuple[bool, str]:
        edge = self._edges.get(edge_id)
        if edge is None:
            return False, "unknown-edge"
        if self.config.require_provenance and not edge.source_ids:
            return False, "no-provenance"
        if edge.evidence_confidence < self.config.min_evidence_confidence:
            return False, "weak-evidence"
        return True, ""

    # -- updates -----------------------------------------------------------

    def record_outcome(self, record: OutcomeRecord) -> list[AssociationUpdate]:
        """Apply one outcome to the edges on the path that produced it."""
        if not self.config.enabled:
            return []
        weights = self.state.current_weights()
        applied: list[AssociationUpdate] = []
        for edge_id in record.path_edges:
            prior = weights.get(edge_id)
            if prior is None:
                self.refusals.append((edge_id, "unknown-edge"))
                continue
            if record.outcome == GOOD:
                allowed, why = self._may_strengthen(edge_id)
                if not allowed:
                    self.refusals.append((edge_id, why))
                    continue
                new = min(
                    self.config.max_association, prior + self.config.reinforce_step
                )
                reason = "outcome-reinforcement"
            else:
                step = (
                    self.config.weaken_step * 2.0
                    if record.outcome == HARMFUL
                    else self.config.weaken_step
                )
                new = max(self.config.min_association, prior - step)
                reason = (
                    "harmful-outcome-penalty"
                    if record.outcome == HARMFUL
                    else "negative-feedback"
                )
            if abs(new - prior) < 1e-12:
                continue
            update = AssociationUpdate(
                edge_id=edge_id,
                prior_weight=prior,
                new_weight=new,
                reason=reason,
                outcome=record.outcome,
                cue=record.cue,
            )
            self.state.record(update)
            applied.append(update)
            weights[edge_id] = new
        return applied

    def decay_unused(self, used_edge_ids: set[str]) -> list[AssociationUpdate]:
        """Association decay: routes not used drift back toward the base.

        Distinct from activation decay (within one traversal) and from
        forgetting (whether a memory should influence behaviour at all).
        """
        if not self.config.enabled or self.config.idle_decay <= 0.0:
            return []
        weights = self.state.current_weights()
        applied: list[AssociationUpdate] = []
        for edge_id, current in sorted(weights.items()):
            if edge_id in used_edge_ids:
                continue
            base = self.state.base_weights.get(edge_id, current)
            if current <= base:
                continue
            new = max(base, current - self.config.idle_decay)
            update = AssociationUpdate(
                edge_id=edge_id,
                prior_weight=current,
                new_weight=new,
                reason="idle-decay",
                outcome="none",
            )
            self.state.record(update)
            applied.append(update)
        return applied

    def frequency_only_update(self, edge_ids) -> list[AssociationUpdate]:
        """The mechanism the book refuses, implemented for E5-H only.

        Strengthening on retrieval count alone is what turns a wrong
        association into a self-confirming one. It exists here so the
        pathology can be demonstrated on a fixture, never as a default.
        """
        weights = self.state.current_weights()
        applied: list[AssociationUpdate] = []
        for edge_id in edge_ids:
            prior = weights.get(edge_id)
            if prior is None:
                continue
            new = min(self.config.max_association, prior + self.config.reinforce_step)
            if abs(new - prior) < 1e-12:
                continue
            update = AssociationUpdate(
                edge_id=edge_id,
                prior_weight=prior,
                new_weight=new,
                reason="retrieval-frequency (refused mechanism; E5-H only)",
                outcome="none",
            )
            self.state.record(update)
            applied.append(update)
            weights[edge_id] = new
        return applied


def path_edge_ids(state, memory) -> tuple[str, ...]:
    """Edge identifiers along one activated memory's best-parent route."""
    edges: list[str] = []
    path = memory.path or []
    for index in range(1, len(path)):
        parent = state.best_parent.get(path[index])
        if parent is not None:
            edges.append(parent[1])
    return tuple(edges)
