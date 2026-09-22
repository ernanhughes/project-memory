"""The memory graph Chapter 5 propagates over.

Chapter 4 produces persistent derived structure. This module defines the
*minimum* that structure must expose for activation to travel through it —
nodes, edges, descriptions, relation labels, and source provenance — and
nothing more. Microsoft GraphRAG is one producer of such a graph; the
deterministic ledger fixture is another; a future backend is a third.

Four quantities are kept deliberately separate throughout this package
(book Chapter 5, "association is not truth"):

``relation``
    What the edge asserts about the world. A semantic fact, grounded in
    source evidence.
``association``
    How readily one memory should evoke another during recall. A
    retrieval priority, not a claim about the world.
``evidence_confidence``
    How well the underlying proposition is supported. Epistemic.
``activation``
    How strongly a node is lit up by the current cue. Per-query,
    transient, and never stored on the node — it lives in
    ``activation.state.ActivationState``.

Collapsing any two of these into one number is the design error this
chapter exists to avoid.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Node kinds. ``source`` nodes are the provenance anchor: every path must
# be able to terminate on raw evidence (HippoRAG 2's passage nodes and
# MemORAI's turn nodes solve the same problem).
ENTITY = "entity"
CLAIM = "claim"
SOURCE = "source"
COMMUNITY = "community"
NODE_KINDS = (ENTITY, CLAIM, SOURCE, COMMUNITY)


@dataclass
class MemoryNode:
    """One addressable memory element."""

    node_id: str
    kind: str
    label: str
    description: str = ""
    # Canonical artifact identifiers this node is evidenced by. For a
    # ``source`` node this is itself.
    source_ids: tuple[str, ...] = ()
    # Free-form tags used only for cue matching and diagnostics.
    terms: tuple[str, ...] = ()
    timestamp: str | None = None
    # True when Chapter 4 derived this node rather than reading it from a
    # source artifact. Derived state is fallible state.
    derived: bool = True

    def __post_init__(self) -> None:
        if self.kind not in NODE_KINDS:
            raise ValueError(f"unknown node kind: {self.kind}")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MemoryEdge:
    """One relationship, with its four quantities kept apart."""

    edge_id: str
    source: str
    target: str
    relation: str
    description: str = ""
    # Retrieval priority. Stage A derives this structurally; Stage B may
    # adapt it from outcomes. It never means "more true".
    association: float = 0.5
    # Epistemic support for the proposition the relation asserts.
    evidence_confidence: float = 0.5
    source_ids: tuple[str, ...] = ()
    # Traversable in both directions? Most memory relations are: knowing
    # that adr-007 supersedes adr-003 should make either reachable from
    # the other. Asymmetric ones (derivation echoes) are marked False.
    bidirectional: bool = True
    derived: bool = True
    # Set on fixtures that deliberately inject a Chapter 4 mistake.
    injected_error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MemoryGraph:
    """Nodes, edges, and the indexes propagation needs."""

    nodes: dict[str, MemoryNode] = field(default_factory=dict)
    edges: list[MemoryEdge] = field(default_factory=list)
    version: str = "unversioned"
    corpus_version: str = "unspecified"
    notes: str = ""

    # -- construction -------------------------------------------------

    def add_node(self, node: MemoryNode) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"duplicate node id: {node.node_id}")
        self.nodes[node.node_id] = node
        self._adjacency = None

    def add_edge(self, edge: MemoryEdge) -> None:
        for endpoint in (edge.source, edge.target):
            if endpoint not in self.nodes:
                raise ValueError(
                    f"edge {edge.edge_id} references unknown node {endpoint}"
                )
        self.edges.append(edge)
        self._adjacency = None

    # -- indexes --------------------------------------------------------

    _adjacency: dict[str, list[tuple[str, MemoryEdge]]] | None = field(
        default=None, repr=False, compare=False
    )

    def adjacency(self) -> dict[str, list[tuple[str, MemoryEdge]]]:
        """neighbour lists as ``node_id -> [(other_id, edge), ...]``."""
        if self._adjacency is not None:
            return self._adjacency
        table: dict[str, list[tuple[str, MemoryEdge]]] = defaultdict(list)
        for edge in self.edges:
            table[edge.source].append((edge.target, edge))
            if edge.bidirectional:
                table[edge.target].append((edge.source, edge))
        # Deterministic order: propagation results must not depend on
        # dict insertion accidents.
        self._adjacency = {
            key: sorted(value, key=lambda item: (item[0], item[1].edge_id))
            for key, value in sorted(table.items())
        }
        return self._adjacency

    def neighbours(self, node_id: str) -> list[tuple[str, MemoryEdge]]:
        return self.adjacency().get(node_id, [])

    def degree(self, node_id: str) -> int:
        return len(self.neighbours(node_id))

    def node_ids(self) -> list[str]:
        return sorted(self.nodes)

    def sources_for(self, node_ids: list[str]) -> list[str]:
        """Canonical artifact ids behind a set of nodes, order-preserving."""
        seen: list[str] = []
        for node_id in node_ids:
            node = self.nodes.get(node_id)
            if node is None:
                continue
            for source_id in node.source_ids:
                if source_id not in seen:
                    seen.append(source_id)
        return seen

    def hubs(self, top: int = 5) -> list[tuple[str, int]]:
        ranked = sorted(
            ((nid, self.degree(nid)) for nid in self.nodes),
            key=lambda item: (-item[1], item[0]),
        )
        return ranked[:top]

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "corpus_version": self.corpus_version,
            "notes": self.notes,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "MemoryGraph":
        graph = cls(
            version=payload.get("version", "unversioned"),
            corpus_version=payload.get("corpus_version", "unspecified"),
            notes=payload.get("notes", ""),
        )
        for item in payload.get("nodes", []):
            data = dict(item)
            data["source_ids"] = tuple(data.get("source_ids", ()))
            data["terms"] = tuple(data.get("terms", ()))
            graph.add_node(MemoryNode(**data))
        for item in payload.get("edges", []):
            data = dict(item)
            data["source_ids"] = tuple(data.get("source_ids", ()))
            graph.add_edge(MemoryEdge(**data))
        return graph

    @classmethod
    def load(cls, path: Path) -> "MemoryGraph":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    # -- controls ---------------------------------------------------------

    def with_shuffled_edges(self, seed: int = 0) -> "MemoryGraph":
        """Degree-preserving edge rewiring: the 'do the edges matter?' control.

        Borrowed from the temporal-shuffle control in the predictive
        associative memory work: if propagation over a rewired graph scores
        the same as over the real one, the associations carried no
        information and any gain came from something else.
        """
        import random

        rng = random.Random(seed)
        endpoints = [(edge.source, edge.target) for edge in self.edges]
        targets = [target for _, target in endpoints]
        rng.shuffle(targets)
        shuffled = MemoryGraph(
            version=f"{self.version}+shuffled{seed}",
            corpus_version=self.corpus_version,
            notes="degree-preserving rewiring control",
        )
        for node in self.nodes.values():
            shuffled.add_node(MemoryNode(**asdict(node)))
        for edge, target in zip(self.edges, targets):
            data = asdict(edge)
            data["target"] = target
            if data["source"] == data["target"]:
                continue
            shuffled.add_edge(MemoryEdge(**data))
        return shuffled

    def with_injected_error(
        self,
        edge_id: str,
        source: str,
        target: str,
        relation: str,
        association: float = 0.9,
    ) -> "MemoryGraph":
        """Copy of the graph plus one deliberately wrong derived relation.

        Chapter 4 extraction is fallible. E5-F asks what a single false
        edge does to propagation, so the error has to be injectable and
        labelled rather than hunted for.
        """
        corrupted = MemoryGraph.from_dict(self.to_dict())
        corrupted.version = f"{self.version}+falseedge:{edge_id}"
        corrupted.add_edge(
            MemoryEdge(
                edge_id=edge_id,
                source=source,
                target=target,
                relation=relation,
                description="injected extraction error",
                association=association,
                evidence_confidence=0.0,
                source_ids=(),
                derived=True,
                injected_error="fabricated relation",
            )
        )
        return corrupted


def from_graphrag_snapshot(snapshot, text_unit_sources=None) -> MemoryGraph:
    """Adapt a Chapter 4 ``GraphSnapshot`` into a Chapter 5 memory graph.

    Chapter 5 consumes the ``StructuredMemoryBackend`` boundary, never
    GraphRAG internals. The snapshot's entities become entity nodes, its
    relationships become edges, its claims become claim nodes, and its
    text units resolve to source nodes so every path can end on evidence.

    ``snapshot`` is duck-typed rather than imported so this package does
    not depend on the Chapter 4 package being installed.
    """
    mapping = text_unit_sources or {}
    graph = MemoryGraph(version="graphrag-snapshot", notes="from Chapter 4")

    def sources_of(unit_ids) -> tuple[str, ...]:
        found: list[str] = []
        for unit in unit_ids or ():
            for doc in mapping.get(unit, [unit]):
                if doc not in found:
                    found.append(doc)
        return tuple(found)

    by_name: dict[str, str] = {}
    for entity in snapshot.entities:
        node_id = f"entity:{entity.name}"
        if node_id in graph.nodes:
            continue
        graph.add_node(
            MemoryNode(
                node_id=node_id,
                kind=ENTITY,
                label=entity.name,
                description=entity.description,
                source_ids=sources_of(entity.source_text_units),
                terms=tuple(entity.name.lower().split()),
            )
        )
        by_name[entity.name] = node_id

    seen_sources: set[str] = set()
    for node in list(graph.nodes.values()):
        for source_id in node.source_ids:
            source_node = f"source:{source_id}"
            if source_node in seen_sources:
                continue
            seen_sources.add(source_node)
            graph.add_node(
                MemoryNode(
                    node_id=source_node,
                    kind=SOURCE,
                    label=source_id,
                    description="",
                    source_ids=(source_id,),
                    derived=False,
                )
            )

    for index, relationship in enumerate(snapshot.relationships):
        head = by_name.get(relationship.source)
        tail = by_name.get(relationship.target)
        if head is None or tail is None:
            continue
        graph.add_edge(
            MemoryEdge(
                edge_id=f"rel:{index}",
                source=head,
                target=tail,
                relation="RELATED_TO",
                description=relationship.description,
                association=min(1.0, max(0.1, relationship.weight / 10.0)),
                evidence_confidence=0.5,
                source_ids=sources_of(relationship.source_text_units),
            )
        )

    for index, claim in enumerate(snapshot.claims):
        node_id = f"claim:{index}"
        graph.add_node(
            MemoryNode(
                node_id=node_id,
                kind=CLAIM,
                label=claim.claim_type or "claim",
                description=claim.description,
                source_ids=sources_of(claim.source_text_units),
            )
        )
        subject = by_name.get(claim.subject)
        if subject is not None:
            graph.add_edge(
                MemoryEdge(
                    edge_id=f"claimedge:{index}",
                    source=subject,
                    target=node_id,
                    relation="SUBJECT_OF",
                    association=0.6,
                    evidence_confidence=0.5,
                    source_ids=sources_of(claim.source_text_units),
                )
            )

    # Bind every node to the source nodes that evidence it, so provenance
    # is reachable by traversal and not only by lookup.
    for node in list(graph.nodes.values()):
        if node.kind == SOURCE:
            continue
        for source_id in node.source_ids:
            source_node = f"source:{source_id}"
            if source_node not in graph.nodes:
                continue
            graph.add_edge(
                MemoryEdge(
                    edge_id=f"evidence:{node.node_id}->{source_id}",
                    source=node.node_id,
                    target=source_node,
                    relation="EVIDENCED_BY",
                    association=0.4,
                    evidence_confidence=0.9,
                    source_ids=(source_id,),
                    derived=False,
                )
            )
    return graph
