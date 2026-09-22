"""Retrieval causality: why did this memory become active?

A retrieval trace answers a different question from a provenance chain.
Provenance answers *why should I believe this claim* and terminates on
source evidence. A trace answers *why did this memory reach my context*
and terminates on the cue. Conflating them would let a frequently
travelled route masquerade as support for what it leads to.

The trace is therefore emitted with an explicit disclaimer in its own
rendering, and the source identifiers it carries are the ones the graph
already recorded — the trace never manufactures evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TraceStep:
    from_node: str
    from_label: str
    to_node: str
    to_label: str
    relation: str
    edge_id: str
    edge_weight: float
    delivered: float


@dataclass
class MemoryTrace:
    """The route from cue to one admitted memory."""

    node_id: str
    label: str
    activation: float
    hops: int
    steps: list[TraceStep] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    seeded_from: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "memory": self.node_id,
            "label": self.label,
            "activation": round(self.activation, 6),
            "hops": self.hops,
            "path": [self.steps[0].from_node] + [s.to_node for s in self.steps]
            if self.steps
            else [self.node_id],
            "relations": [step.relation for step in self.steps],
            "source_evidence": list(self.source_ids),
            "seeded_from": list(self.seeded_from),
        }

    def render(self) -> str:
        lines = [f"{self.node_id} ({self.label})  activation={self.activation:.3f}"]
        if not self.steps:
            lines.append("  seeded directly by the cue")
        for step in self.steps:
            lines.append(
                f"  {step.from_label} --{step.relation}--> {step.to_label}"
                f"   (w={step.edge_weight:.2f}, delivered={step.delivered:.3f})"
            )
        if self.source_ids:
            lines.append(f"  evidence: {', '.join(self.source_ids)}")
        return "\n".join(lines)


def build_trace(graph, state, memory) -> MemoryTrace:
    """Reconstruct the strongest route that activated one memory."""
    path = memory.path or [memory.node_id]
    steps: list[TraceStep] = []
    for index in range(1, len(path)):
        parent_id = path[index - 1]
        child_id = path[index]
        event = None
        for candidate in state.events:
            if candidate.source == parent_id and candidate.target == child_id:
                if event is None or candidate.delivered > event.delivered:
                    event = candidate
        if event is None:
            continue
        steps.append(
            TraceStep(
                from_node=parent_id,
                from_label=graph.nodes[parent_id].label
                if parent_id in graph.nodes
                else parent_id,
                to_node=child_id,
                to_label=graph.nodes[child_id].label
                if child_id in graph.nodes
                else child_id,
                relation=event.relation,
                edge_id=event.edge_id,
                edge_weight=event.edge_weight,
                delivered=event.delivered,
            )
        )
    return MemoryTrace(
        node_id=memory.node_id,
        label=memory.label,
        activation=memory.activation,
        hops=memory.hops,
        steps=steps,
        source_ids=list(memory.source_ids),
        seeded_from=[path[0]] if path else [],
    )


def explain(graph, result, limit: int = 5) -> str:
    """Human-readable account of an associative retrieval."""
    lines = [
        f"cue: {result.cue}",
        f"strategy: {result.strategy}",
        "seeds: "
        + ", ".join(
            f"{seed.node_id}({seed.score:.2f})" for seed in result.seeds
        )
        or "seeds: none",
        "",
        "This is a retrieval trace: it records why each memory became "
        "active, not whether what it says is true.",
        "",
    ]
    for memory in result.admitted[:limit]:
        lines.append(build_trace(graph, result.state, memory).render())
        lines.append("")
    lines.append(
        f"explored {len(result.explored)} memories to admit "
        f"{len(result.admitted)} (expansion factor "
        f"{result.expansion_factor():.1f}); stopped because "
        f"{result.terminated_because}"
    )
    return "\n".join(lines)
