"""Graph abstraction, fixture integrity, and controls."""

from dataclasses import replace

import pytest

from associative_memory.fixtures import ARTIFACTS, CUES, build_cases, build_graph
from associative_memory.graph.adapter import (
    ENTITY,
    SOURCE,
    MemoryEdge,
    MemoryGraph,
    MemoryNode,
)


def tiny_graph() -> MemoryGraph:
    graph = MemoryGraph(version="tiny")
    for name in ("a", "b", "c"):
        graph.add_node(
            MemoryNode(node_id=name, kind=ENTITY, label=name, terms=(name,))
        )
    graph.add_edge(
        MemoryEdge(edge_id="ab", source="a", target="b", relation="R",
                   source_ids=("s1",))
    )
    graph.add_edge(
        MemoryEdge(edge_id="bc", source="b", target="c", relation="R",
                   source_ids=("s2",))
    )
    return graph


def test_duplicate_node_rejected() -> None:
    graph = tiny_graph()
    with pytest.raises(ValueError):
        graph.add_node(MemoryNode(node_id="a", kind=ENTITY, label="a"))


def test_edge_to_unknown_node_rejected() -> None:
    graph = tiny_graph()
    with pytest.raises(ValueError):
        graph.add_edge(
            MemoryEdge(edge_id="ax", source="a", target="zz", relation="R")
        )


def test_unknown_node_kind_rejected() -> None:
    with pytest.raises(ValueError):
        MemoryNode(node_id="x", kind="not-a-kind", label="x")


def test_adjacency_is_deterministic_and_bidirectional() -> None:
    graph = tiny_graph()
    first = {k: [n for n, _ in v] for k, v in graph.adjacency().items()}
    graph._adjacency = None
    second = {k: [n for n, _ in v] for k, v in graph.adjacency().items()}
    assert first == second
    assert "a" in first["b"] and "c" in first["b"]


def test_directed_edge_is_not_traversable_backwards() -> None:
    graph = tiny_graph()
    graph.add_edge(
        MemoryEdge(
            edge_id="ca", source="c", target="a", relation="ECHOES",
            bidirectional=False,
        )
    )
    assert "a" in [n for n, _ in graph.neighbours("c")]
    assert "c" not in [n for n, _ in graph.neighbours("a")]


def test_round_trip_serialisation() -> None:
    graph = build_graph()
    restored = MemoryGraph.from_dict(graph.to_dict())
    assert restored.node_ids() == graph.node_ids()
    assert [e.edge_id for e in restored.edges] == [e.edge_id for e in graph.edges]
    assert restored.version == graph.version


def test_shuffle_control_preserves_edge_budget() -> None:
    graph = build_graph()
    shuffled = graph.with_shuffled_edges(seed=3)
    assert shuffled.node_ids() == graph.node_ids()
    # Rewiring may drop self-loops, never add edges.
    assert len(shuffled.edges) <= len(graph.edges)
    assert shuffled.version != graph.version
    assert [e.edge_id for e in shuffled.edges] != [] # still a graph


def test_shuffle_is_reproducible() -> None:
    graph = build_graph()
    first = graph.with_shuffled_edges(seed=3)
    second = graph.with_shuffled_edges(seed=3)
    assert [(e.source, e.target) for e in first.edges] == [
        (e.source, e.target) for e in second.edges
    ]


def test_injected_error_is_labelled_and_unprovenanced() -> None:
    graph = build_graph()
    corrupted = graph.with_injected_error(
        "bad-1", "claim:evt-205", "source:incident-106", "SUPPORTED_BY"
    )
    edge = next(e for e in corrupted.edges if e.edge_id == "bad-1")
    assert edge.injected_error
    assert edge.source_ids == ()
    assert edge.evidence_confidence == 0.0
    assert len(corrupted.edges) == len(graph.edges) + 1
    # The original is untouched: derived state is rebuildable, not mutated.
    assert all(e.edge_id != "bad-1" for e in graph.edges)


# -- fixture integrity ---------------------------------------------------


def test_every_fixture_source_node_uses_a_ledger_identifier() -> None:
    """No invented artifact identifiers may enter the fixture."""
    ledger = {artifact_id for artifact_id, _k, _d, _desc in ARTIFACTS}
    graph = build_graph()
    for node in graph.nodes.values():
        for source_id in node.source_ids:
            assert source_id in ledger, source_id


def test_every_expected_source_is_reachable_in_the_graph() -> None:
    graph = build_graph()
    known = {
        source_id
        for node in graph.nodes.values()
        for source_id in node.source_ids
    }
    for case in build_cases():
        for source_id in case.expected_sources:
            assert source_id in known, f"{case.case_id}: {source_id}"
        for source_id in case.distractor_sources:
            assert source_id in known, f"{case.case_id}: {source_id}"


def test_every_expected_path_node_exists() -> None:
    graph = build_graph()
    for case in build_cases():
        for node_id in case.expected_path:
            assert node_id in graph.nodes, f"{case.case_id}: {node_id}"


def test_case_ids_are_unique_and_cover_every_hop_class() -> None:
    cases = build_cases()
    assert len({case.case_id for case in cases}) == len(cases)
    classes = {case.hop_class for case in cases}
    assert {"direct", "indirect", "adversarial", "unanswerable"} <= classes


def test_unanswerable_case_expects_no_sources() -> None:
    cases = {case.case_id: case for case in build_cases()}
    case = cases["c-abs-cache"]
    assert case.expected_sources == ()
    assert case.expected_status == "unanswerable"


def test_fixture_graph_contains_the_designed_traps() -> None:
    graph = build_graph()
    relations = {edge.relation for edge in graph.edges}
    # Derived echoes, a same-symptom trap, and a supersession must exist,
    # or the adversarial cases are not testing anything.
    assert "DERIVED_FROM" in relations
    assert "ECHOES" in relations
    assert "RESEMBLES" in relations
    assert "SUPERSEDES" in relations
    # And there must be a genuine hub.
    top_degree = graph.hubs(1)[0][1]
    assert top_degree >= 3 * (len(graph.edges) * 2 / len(graph.nodes))


def test_graph_contains_cycles_on_purpose() -> None:
    from associative_memory.health.checks import check_graph

    assert check_graph(build_graph()).cycles_detected


def test_sources_for_is_order_preserving_and_deduplicated() -> None:
    graph = build_graph()
    ids = graph.sources_for(["claim:evt-205", "source:adr-007", "claim:evt-205"])
    assert ids == ["adr-007"]


def test_from_graphrag_snapshot_builds_provenance_edges() -> None:
    """Chapter 5 consumes the Chapter 4 boundary, not GraphRAG internals."""
    from associative_memory.graph.adapter import from_graphrag_snapshot

    class FakeEntity:
        def __init__(self, name):
            self.name = name
            self.description = f"description of {name}"
            self.source_text_units = ["u1"]
            self.degree = 1

    class FakeRelationship:
        def __init__(self, source, target):
            self.source = source
            self.target = target
            self.description = "relates"
            self.weight = 5.0
            self.source_text_units = ["u1"]

    class FakeSnapshot:
        entities = [FakeEntity("PostgreSQL"), FakeEntity("SQLite")]
        relationships = [FakeRelationship("PostgreSQL", "SQLite")]
        claims = []
        communities = []
        text_units = 1
        documents = 1

    graph = from_graphrag_snapshot(
        FakeSnapshot(), text_unit_sources={"u1": ["adr-007.md"]}
    )
    assert "entity:PostgreSQL" in graph.nodes
    assert "source:adr-007.md" in graph.nodes
    assert graph.nodes["source:adr-007.md"].kind == SOURCE
    assert graph.nodes["source:adr-007.md"].derived is False
    assert any(edge.relation == "EVIDENCED_BY" for edge in graph.edges)


def test_config_fields_survive_replace() -> None:
    from associative_memory.config import AssociativeConfig

    config = AssociativeConfig()
    variant = replace(
        config, propagation=replace(config.propagation, max_hops=9)
    )
    assert variant.propagation.max_hops == 9
    assert config.propagation.max_hops == 3
    assert "max_hops" in variant.to_dict()["propagation"]
