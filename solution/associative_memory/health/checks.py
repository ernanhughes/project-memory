"""Graph and pathway health.

Structural health is not memory quality. A graph can be perfectly
connected, fully provenanced, and evenly weighted while answering every
question wrongly. These checks say only whether the substrate deserves to
be measured at all; Chapter 2's instrument says whether its memory is any
good. The distinction is stated here because the two are easy to confuse
in a dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HealthIssue:
    check: str
    detail: str


@dataclass
class GraphHealthReport:
    healthy: bool = True
    nodes: int = 0
    semantic_edges: int = 0
    edges_without_provenance: int = 0
    derived_edges: int = 0
    injected_errors: int = 0
    average_degree: float = 0.0
    max_degree: int = 0
    hubs: list[tuple[str, int]] = field(default_factory=list)
    orphan_nodes: list[str] = field(default_factory=list)
    nodes_without_sources: int = 0
    cycles_detected: bool = False
    min_association: float = 0.0
    max_association: float = 0.0
    # Adaptive-state fields, populated only when a learner is running.
    policy_version: str | None = None
    base_graph_version: str | None = None
    updates_total: int = 0
    strengthened: int = 0
    weakened: int = 0
    decayed: int = 0
    last_update: str | None = None
    stale_pathways: int = 0
    issues: list[HealthIssue] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "Associative Memory Health",
            "",
            f"Nodes:                    {self.nodes}",
            f"Semantic edges:           {self.semantic_edges}",
            f"Derived edges:            {self.derived_edges}",
            f"Edges without provenance: {self.edges_without_provenance}",
            f"Nodes without sources:    {self.nodes_without_sources}",
            f"Average degree:           {self.average_degree:.2f}",
            f"Max degree:               {self.max_degree}",
            f"Cycles present:           {'yes' if self.cycles_detected else 'no'}",
            f"Association range:        "
            f"{self.min_association:.2f}-{self.max_association:.2f}",
        ]
        if self.hubs:
            listed = ", ".join(f"{nid}({deg})" for nid, deg in self.hubs)
            lines.append(f"Highest-degree nodes:     {listed}")
        if self.orphan_nodes:
            lines.append(f"Orphan nodes:             {len(self.orphan_nodes)}")
        if self.injected_errors:
            lines.append(
                f"Injected false edges:     {self.injected_errors} (fixture)"
            )
        if self.policy_version:
            lines += [
                "",
                f"Association policy:       {self.policy_version}",
                f"Base graph version:       {self.base_graph_version}",
                f"Updates recorded:         {self.updates_total}",
                f"  strengthened:           {self.strengthened}",
                f"  weakened:               {self.weakened}",
                f"  decayed:                {self.decayed}",
                f"Last update:              {self.last_update or '-'}",
                f"Stale pathways:           {self.stale_pathways}",
            ]
        lines.append("")
        if self.issues:
            lines.append("Issues:")
            for issue in self.issues:
                lines.append(f"  [{issue.check}] {issue.detail}")
        else:
            lines.append("No structural issues detected.")
        lines.append(f"Verdict: {'HEALTHY' if self.healthy else 'UNHEALTHY'}")
        lines.append(
            "Structural health is not memory quality; see the Chapter 2 "
            "scorecard for that."
        )
        return "\n".join(lines) + "\n"


def _has_cycle(graph) -> bool:
    """Any cycle in the traversable (undirected-where-bidirectional) graph."""
    adjacency = graph.adjacency()
    seen: set[str] = set()
    for start in graph.node_ids():
        if start in seen:
            continue
        stack = [(start, None)]
        local: dict[str, str | None] = {}
        while stack:
            node, parent_edge = stack.pop()
            if node in local:
                continue
            local[node] = parent_edge
            seen.add(node)
            for neighbour, edge in adjacency.get(node, []):
                if neighbour in local and edge.edge_id != parent_edge:
                    return True
                if neighbour not in local:
                    stack.append((neighbour, edge.edge_id))
    return False


def check_graph(graph, association_state=None) -> GraphHealthReport:
    report = GraphHealthReport(
        nodes=len(graph.nodes),
        semantic_edges=len(graph.edges),
        derived_edges=sum(1 for edge in graph.edges if edge.derived),
        edges_without_provenance=sum(
            1 for edge in graph.edges if not edge.source_ids
        ),
        injected_errors=sum(
            1 for edge in graph.edges if edge.injected_error
        ),
        nodes_without_sources=sum(
            1 for node in graph.nodes.values() if not node.source_ids
        ),
        hubs=graph.hubs(top=5),
    )
    degrees = [graph.degree(node_id) for node_id in graph.nodes]
    report.average_degree = (sum(degrees) / len(degrees)) if degrees else 0.0
    report.max_degree = max(degrees) if degrees else 0
    report.orphan_nodes = [
        node_id for node_id in graph.node_ids() if graph.degree(node_id) == 0
    ]
    report.cycles_detected = _has_cycle(graph)
    weights = [edge.association for edge in graph.edges] or [0.0]
    report.min_association = min(weights)
    report.max_association = max(weights)

    def flag(check: str, detail: str) -> None:
        report.issues.append(HealthIssue(check, detail))
        report.healthy = False

    if report.nodes == 0:
        flag("empty-graph", "no nodes")
    if report.orphan_nodes:
        flag(
            "orphan-nodes",
            f"{len(report.orphan_nodes)} nodes are unreachable by traversal",
        )
    if report.edges_without_provenance:
        flag(
            "unprovenanced-edges",
            f"{report.edges_without_provenance} edges carry no source ids; "
            "these can never be strengthened by the learner",
        )
    if report.max_degree > max(10, 4 * report.average_degree):
        flag(
            "dominant-hub",
            f"highest-degree node has {report.max_degree} neighbours against "
            f"an average of {report.average_degree:.1f}; expect hub capture",
        )
    if report.max_association > 0.95:
        flag(
            "saturated-association",
            "an association weight has reached the ceiling; check for "
            "runaway reinforcement",
        )

    if association_state is not None:
        report.policy_version = association_state.policy_version
        report.base_graph_version = association_state.base_graph_version
        report.updates_total = len(association_state.updates)
        report.strengthened = sum(
            1
            for update in association_state.updates
            if update.new_weight > update.prior_weight
        )
        report.weakened = sum(
            1
            for update in association_state.updates
            if update.new_weight < update.prior_weight
            and update.reason != "idle-decay"
        )
        report.decayed = sum(
            1
            for update in association_state.updates
            if update.reason == "idle-decay"
        )
        report.last_update = (
            association_state.updates[-1].timestamp
            if association_state.updates
            else None
        )
        current = association_state.current_weights()
        report.stale_pathways = sum(
            1
            for edge_id, weight in current.items()
            if weight > association_state.base_weights.get(edge_id, weight)
            and not association_state.history_for(edge_id)
        )
        frequency_updates = [
            update
            for update in association_state.updates
            if update.reason.startswith("retrieval-frequency")
        ]
        if frequency_updates:
            flag(
                "frequency-reinforcement",
                f"{len(frequency_updates)} weights were raised by retrieval "
                "count alone; this mechanism is refused outside E5-H",
            )
    return report
