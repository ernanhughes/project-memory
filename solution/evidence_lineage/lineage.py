"""The evidence/lineage DAG.

Edge taxonomy (each type has exactly one meaning and one use):

* SUPPORTED_BY — evidential: this evidence contributes to licensing
  the claim. Use: verification, support groups, impact analysis.
* DERIVED_FROM — lineage: this object was generated, summarised,
  extracted or computed from the parent. Never means the parent
  proves the child. Use: backward traces, error localisation.
* ECHO_OF — restatement: this content propagates earlier information
  rather than contributing independent evidence. Use: preventing
  repetition from masquerading as corroboration.
* REFUTES — evidence against a claim. Recorded only; Chapter 7 never
  resolves conflicts (Chapter 8 territory).

Rules enforced structurally:

* DERIVED_FROM is never treated as SUPPORTED_BY (no auto-conversion).
* Retrieval/control traces (Ch5 paths, Ch6 routes) are stored as node
  attributes, never as support edges.
* DERIVED_FROM must be acyclic; ECHO_OF must resolve to a non-echo
  source (no echo-only grounding).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NodeKind(str, Enum):
    CLAIM = "claim"
    SOURCE_SPAN = "source_span"
    DERIVED = "derived"  # extraction, graph node, summary, context, answer


class EdgeKind(str, Enum):
    SUPPORTED_BY = "SUPPORTED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    ECHO_OF = "ECHO_OF"
    REFUTES = "REFUTES"


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind
    label: str = ""
    # Traceability boundary note: raw spans are inspectable history,
    # not truth. A raw node may be mistaken, stale or deceptive.
    payload: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Edge:
    source: str  # the dependent (claim, derived object)
    target: str  # what it depends on
    kind: EdgeKind
    extractor: str = "fixture"
    extractor_version: str = "ledger-deterministic-v0.1"
    extraction_confidence: float = 1.0
    # Provenance of provenance: what licensed this edge.
    licensed_by: tuple[str, ...] = ()


@dataclass
class LineageGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    # Retrieval causality and control causality, kept as annotations
    # so they can never be mistaken for evidential support.
    retrieval_traces: dict[str, list[str]] = field(default_factory=dict)
    control_traces: dict[str, list[str]] = field(default_factory=dict)

    # -- construction -------------------------------------------------

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise ValueError(
                f"dangling edge {edge.source} -> {edge.target}")
        if edge.kind == EdgeKind.DERIVED_FROM and self._reaches(
                edge.target, edge.source, EdgeKind.DERIVED_FROM):
            raise ValueError(
                f"DERIVED_FROM cycle rejected: {edge.source} -> "
                f"{edge.target}")
        self.edges.append(edge)

    def _reaches(self, start: str, goal: str, kind: EdgeKind) -> bool:
        seen = {start}
        stack = [start]
        while stack:
            node = stack.pop()
            for edge in self.edges:
                if edge.kind == kind and edge.source == node:
                    if edge.target == goal:
                        return True
                    if edge.target not in seen:
                        seen.add(edge.target)
                        stack.append(edge.target)
        return False

    # -- queries ------------------------------------------------------

    def outgoing(self, node_id: str,
                 kind: EdgeKind | None = None) -> list[Edge]:
        return [e for e in self.edges
                if e.source == node_id and (kind is None or e.kind == kind)]

    def incoming(self, node_id: str,
                 kind: EdgeKind | None = None) -> list[Edge]:
        return [e for e in self.edges
                if e.target == node_id and (kind is None or e.kind == kind)]

    def support_for(self, claim_id: str) -> list[Edge]:
        """Evidential support only. Derivation is never included."""
        return self.outgoing(claim_id, EdgeKind.SUPPORTED_BY)

    def lineage_of(self, node_id: str) -> list[Edge]:
        return self.outgoing(node_id, EdgeKind.DERIVED_FROM)

    def sources_for(self, claim_id: str) -> list[str]:
        """Raw spans reachable via support edges (grounding set)."""
        return [e.target for e in self.support_for(claim_id)
                if self.nodes[e.target].kind == NodeKind.SOURCE_SPAN]

    def dependents_of(self, evidence_id: str) -> list[str]:
        """Forward lookup: which claims transitively depend on this node."""
        dependents: list[str] = []
        seen = {evidence_id}
        stack = [evidence_id]
        while stack:
            node = stack.pop()
            for edge in self.incoming(node):
                if edge.kind in (EdgeKind.SUPPORTED_BY,
                                 EdgeKind.DERIVED_FROM,
                                 EdgeKind.ECHO_OF) \
                        and edge.source not in seen:
                    seen.add(edge.source)
                    stack.append(edge.source)
                    if self.nodes[edge.source].kind == NodeKind.CLAIM:
                        dependents.append(edge.source)
        return sorted(dependents)

    def trace_to_sources(self, claim_id: str) -> dict:
        """Backward trace: claim -> support/derivation -> raw spans.

        Follows SUPPORTED_BY and DERIVED_FROM; resolves ECHO_OF to the
        echoed source instead of counting the echo as evidence.
        """
        trail: list[dict] = []
        visited: set[str] = set()

        def walk(node_id: str, depth: int) -> None:
            if node_id in visited:
                trail.append({"node": node_id, "relation": "already-seen",
                              "depth": depth})
                return
            visited.add(node_id)
            node = self.nodes[node_id]
            if node.kind == NodeKind.SOURCE_SPAN:
                trail.append({"node": node_id, "relation": "GROUND",
                              "depth": depth})
                return
            stepped = False
            for edge in self.outgoing(node_id):
                if edge.kind == EdgeKind.SUPPORTED_BY:
                    trail.append({"node": node_id, "relation": "SUPPORTED_BY",
                                  "target": edge.target, "depth": depth})
                    walk(edge.target, depth + 1)
                    stepped = True
                elif edge.kind == EdgeKind.DERIVED_FROM:
                    trail.append({"node": node_id, "relation": "DERIVED_FROM",
                                  "target": edge.target, "depth": depth})
                    walk(edge.target, depth + 1)
                    stepped = True
                elif edge.kind == EdgeKind.ECHO_OF:
                    trail.append({"node": node_id, "relation": "ECHO_OF",
                                  "target": edge.target, "depth": depth})
                    walk(edge.target, depth + 1)
                    stepped = True
            if not stepped:
                trail.append({"node": node_id, "relation": "OPEN_LINEAGE",
                              "depth": depth})

        walk(claim_id, 0)
        grounded = [t["node"] for t in trail if t["relation"] == "GROUND"]
        open_ends = [t["node"] for t in trail
                     if t["relation"] == "OPEN_LINEAGE"]
        return {"claim": claim_id, "trail": trail,
                "grounded_spans": sorted(set(grounded)),
                "open_lineages": sorted(set(open_ends)),
                "raw_grounded": len(grounded) > 0}

    # -- health -------------------------------------------------------

    def health(self) -> dict:
        """Structural checks. Structural health is not correctness."""
        claims = [n for n in self.nodes.values()
                  if n.kind == NodeKind.CLAIM]
        no_lineage = [n.id for n in claims
                      if not self.outgoing(n.id)]
        dangling = [f"{e.source}->{e.target}" for e in self.edges
                    if e.source not in self.nodes
                    or e.target not in self.nodes]
        derived_no_prov = [
            n.id for n in self.nodes.values()
            if n.kind == NodeKind.DERIVED
            and not self.outgoing(n.id, EdgeKind.DERIVED_FROM)
            and not self.outgoing(n.id, EdgeKind.ECHO_OF)]
        echo_chains = []
        for edge in self.edges:
            if edge.kind == EdgeKind.ECHO_OF:
                resolved = self._resolve_echo(edge.target)
                echo_chains.append({"echo": edge.source,
                                    "resolves_to": resolved})
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "claims": len(claims),
            "claims_with_no_lineage": no_lineage,
            "dangling_edges": dangling,
            "derived_without_provenance": derived_no_prov,
            "echo_resolutions": echo_chains,
        }

    def _resolve_echo(self, node_id: str) -> str:
        seen = set()
        current = node_id
        while current not in seen:
            seen.add(current)
            nxt = [e.target for e in self.outgoing(current)
                   if e.kind == EdgeKind.ECHO_OF]
            if not nxt:
                return current
            current = nxt[0]
        return current
