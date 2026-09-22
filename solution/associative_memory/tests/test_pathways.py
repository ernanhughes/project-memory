"""Traces, versioned association state, learning safeguards, and health."""

from dataclasses import replace

import pytest

from associative_memory.config import AssociativeConfig, LearningConfig
from associative_memory.fixtures import build_cases, build_graph
from associative_memory.health.checks import check_graph
from associative_memory.pathways.learning import (
    BAD,
    GOOD,
    HARMFUL,
    OutcomeRecord,
    PathwayLearner,
    path_edge_ids,
)
from associative_memory.pathways.trace import build_trace, explain
from associative_memory.pathways.weights import AssociationState, AssociationUpdate
from associative_memory.pipeline import AssociativeMemory


@pytest.fixture(scope="module")
def graph():
    return build_graph()


@pytest.fixture(scope="module")
def cases():
    return {case.case_id: case for case in build_cases()}


# -- traces --------------------------------------------------------------


def test_trace_reconstructs_the_route_and_keeps_provenance(graph, cases) -> None:
    memory = AssociativeMemory(
        graph=graph, config=AssociativeConfig(), strategy="spreading"
    )
    result = memory.retrieve(cases["c-hop-why"].cue)
    multi_hop = [item for item in result.admitted if item.hops >= 1]
    assert multi_hop, "no multi-hop memory to trace"
    trace = build_trace(graph, result.state, multi_hop[0])
    assert trace.steps
    for step in trace.steps:
        assert step.relation and step.edge_id
        assert step.from_node in graph.nodes and step.to_node in graph.nodes
    payload = trace.to_dict()
    assert payload["path"][-1] == trace.node_id
    assert "source_evidence" in payload


def test_trace_of_a_seeded_memory_says_so(graph, cases) -> None:
    memory = AssociativeMemory(
        graph=graph, config=AssociativeConfig(), strategy="spreading"
    )
    result = memory.retrieve(cases["c-direct-target"].cue)
    seeded = next(item for item in result.admitted if item.seeded)
    rendered = build_trace(graph, result.state, seeded).render()
    assert "seeded directly by the cue" in rendered


def test_explanation_separates_retrieval_causality_from_truth(graph, cases) -> None:
    memory = AssociativeMemory(
        graph=graph, config=AssociativeConfig(), strategy="conditioned"
    )
    result = memory.retrieve(cases["c-hop-backup"].cue)
    text = explain(graph, result)
    assert "retrieval trace" in text
    assert "not whether what it says is true" in text
    assert "expansion factor" in text


# -- versioned association state --------------------------------------------


def test_association_state_replays_and_rolls_back(graph) -> None:
    state = AssociationState.from_graph(graph, "test-policy")
    base = dict(state.base_weights)
    state.record(
        AssociationUpdate(
            edge_id="e001", prior_weight=base["e001"], new_weight=0.9,
            reason="test", outcome=GOOD,
        )
    )
    state.record(
        AssociationUpdate(
            edge_id="e001", prior_weight=0.9, new_weight=0.95,
            reason="test", outcome=GOOD,
        )
    )
    assert state.current_weights()["e001"] == 0.95
    assert state.weights_at(1)["e001"] == 0.9
    assert state.weights_at(0) == base
    assert state.base_weights == base, "the base must never be mutated"


def test_association_state_explains_a_strong_pathway(graph) -> None:
    state = AssociationState.from_graph(graph, "test-policy")
    assert "never updated" in state.explain("e001")
    state.record(
        AssociationUpdate(
            edge_id="e001", prior_weight=0.85, new_weight=0.9,
            reason="outcome-reinforcement", outcome=GOOD, cue="why",
        )
    )
    text = state.explain("e001")
    assert "outcome-reinforcement" in text and "0.850 -> 0.900" in text


def test_association_state_round_trips_through_disk(graph, tmp_path) -> None:
    state = AssociationState.from_graph(graph, "test-policy")
    state.record(
        AssociationUpdate(
            edge_id="e002", prior_weight=0.8, new_weight=0.85,
            reason="test", outcome=GOOD,
        )
    )
    path = state.save(tmp_path / "assoc.json")
    restored = AssociationState.load(path)
    assert restored.current_weights() == state.current_weights()
    assert restored.policy_version == state.policy_version


def test_apply_to_writes_current_weights_onto_a_working_copy(graph) -> None:
    working = type(graph).from_dict(graph.to_dict())
    state = AssociationState.from_graph(working, "test-policy")
    state.record(
        AssociationUpdate(
            edge_id="e001", prior_weight=0.85, new_weight=0.2,
            reason="test", outcome=BAD,
        )
    )
    state.apply_to(working)
    assert next(e for e in working.edges if e.edge_id == "e001").association == 0.2
    # The graph the fixture builds is untouched.
    assert next(e for e in graph.edges if e.edge_id == "e001").association == 0.85


# -- learning safeguards -------------------------------------------------------


def learner_for(graph, **overrides):
    working = type(graph).from_dict(graph.to_dict())
    config = LearningConfig(enabled=True, **overrides)
    state = AssociationState.from_graph(working, config.policy_version)
    return PathwayLearner(config, state, working), state, working


def test_learning_is_off_by_default(graph) -> None:
    config = LearningConfig()
    assert config.enabled is False
    state = AssociationState.from_graph(graph, config.policy_version)
    learner = PathwayLearner(config, state, graph)
    assert learner.record_outcome(
        OutcomeRecord(cue="c", outcome=GOOD, path_edges=("e001",))
    ) == []
    assert state.updates == []


def test_good_outcome_strengthens_a_well_evidenced_edge(graph) -> None:
    learner, state, _ = learner_for(graph)
    before = state.current_weights()["e003"]
    updates = learner.record_outcome(
        OutcomeRecord(cue="why", outcome=GOOD, path_edges=("e003",))
    )
    assert len(updates) == 1
    assert state.current_weights()["e003"] > before


def test_reinforcement_refuses_an_edge_without_provenance(graph) -> None:
    corrupted = graph.with_injected_error(
        "bad-1", "claim:evt-205", "source:incident-106", "SUPPORTED_BY"
    )
    learner, state, _ = learner_for(corrupted)
    updates = learner.record_outcome(
        OutcomeRecord(cue="c", outcome=GOOD, path_edges=("bad-1",))
    )
    assert updates == []
    assert ("bad-1", "no-provenance") in learner.refusals


def test_reinforcement_refuses_a_weakly_evidenced_edge(graph) -> None:
    learner, state, _ = learner_for(graph)
    # e077 is the staging echo: real provenance, deliberately low
    # evidence confidence. A useful route through it stays weak.
    updates = learner.record_outcome(
        OutcomeRecord(cue="c", outcome=GOOD, path_edges=("e077",))
    )
    assert updates == []
    assert ("e077", "weak-evidence") in learner.refusals


def test_negative_and_harmful_outcomes_weaken_by_different_amounts(graph) -> None:
    learner, state, _ = learner_for(graph)
    before = state.current_weights()["e003"]
    learner.record_outcome(
        OutcomeRecord(cue="c", outcome=BAD, path_edges=("e003",))
    )
    after_bad = state.current_weights()["e003"]
    learner.record_outcome(
        OutcomeRecord(cue="c", outcome=HARMFUL, path_edges=("e003",))
    )
    after_harmful = state.current_weights()["e003"]
    assert before - after_bad == pytest.approx(0.05)
    assert after_bad - after_harmful == pytest.approx(0.10)


def test_weights_are_bounded(graph) -> None:
    learner, state, _ = learner_for(graph)
    for _ in range(100):
        learner.record_outcome(
            OutcomeRecord(cue="c", outcome=GOOD, path_edges=("e003",))
        )
    assert state.current_weights()["e003"] <= learner.config.max_association
    for _ in range(200):
        learner.record_outcome(
            OutcomeRecord(cue="c", outcome=HARMFUL, path_edges=("e003",))
        )
    assert state.current_weights()["e003"] >= learner.config.min_association


def test_unknown_outcome_is_rejected() -> None:
    with pytest.raises(ValueError):
        OutcomeRecord(cue="c", outcome="fantastic", path_edges=())


def test_idle_decay_returns_a_boosted_edge_toward_its_base(graph) -> None:
    learner, state, _ = learner_for(graph)
    learner.record_outcome(
        OutcomeRecord(cue="c", outcome=GOOD, path_edges=("e003",))
    )
    boosted = state.current_weights()["e003"]
    learner.decay_unused(used_edge_ids=set())
    assert state.current_weights()["e003"] < boosted
    for _ in range(50):
        learner.decay_unused(used_edge_ids=set())
    assert state.current_weights()["e003"] == pytest.approx(
        state.base_weights["e003"]
    )


def test_idle_decay_never_falls_below_the_base(graph) -> None:
    learner, state, _ = learner_for(graph)
    for _ in range(20):
        learner.decay_unused(used_edge_ids=set())
    assert state.current_weights() == state.base_weights


def test_frequency_reinforcement_is_available_but_marked_as_refused(graph) -> None:
    learner, state, _ = learner_for(graph)
    learner.frequency_only_update(["e003"])
    update = state.updates[-1]
    assert "refused mechanism" in update.reason
    assert update.outcome == "none"
    report = check_graph(graph, state)
    assert not report.healthy
    assert any(issue.check == "frequency-reinforcement" for issue in report.issues)


def test_frequency_reinforcement_ignores_the_evidence_gates(graph) -> None:
    """The refused mechanism is refused precisely because it does this."""
    corrupted = graph.with_injected_error(
        "bad-1", "claim:evt-205", "source:incident-106", "SUPPORTED_BY",
        association=0.5,
    )
    learner, state, _ = learner_for(corrupted)
    learner.frequency_only_update(["bad-1"])
    assert state.current_weights()["bad-1"] > 0.5
    assert learner.refusals == []


def test_path_edge_ids_returns_the_route(graph, cases) -> None:
    memory = AssociativeMemory(
        graph=graph, config=AssociativeConfig(), strategy="spreading"
    )
    result = memory.retrieve(cases["c-hop-backup"].cue)
    multi_hop = [item for item in result.admitted if item.hops >= 1]
    assert multi_hop
    edges = path_edge_ids(result.state, multi_hop[0])
    assert edges
    known = {edge.edge_id for edge in graph.edges}
    assert all(edge_id in known for edge_id in edges)


# -- health ------------------------------------------------------------------


def test_health_reports_structure_and_flags_the_hub(graph) -> None:
    report = check_graph(graph)
    assert report.nodes == len(graph.nodes)
    assert report.semantic_edges == len(graph.edges)
    assert report.edges_without_provenance == 0
    assert any(issue.check == "dominant-hub" for issue in report.issues)
    rendered = report.render()
    assert "Structural health is not memory quality" in rendered


def test_health_flags_an_unprovenanced_injected_edge(graph) -> None:
    corrupted = graph.with_injected_error(
        "bad-1", "claim:evt-205", "source:incident-106", "SUPPORTED_BY"
    )
    report = check_graph(corrupted)
    assert report.injected_errors == 1
    assert any(issue.check == "unprovenanced-edges" for issue in report.issues)


def test_health_reports_orphans_and_an_empty_graph() -> None:
    from associative_memory.graph.adapter import ENTITY, MemoryGraph, MemoryNode

    empty = MemoryGraph(version="empty")
    assert any(issue.check == "empty-graph" for issue in check_graph(empty).issues)
    lonely = MemoryGraph(version="lonely")
    lonely.add_node(MemoryNode(node_id="x", kind=ENTITY, label="x"))
    report = check_graph(lonely)
    assert report.orphan_nodes == ["x"]
    assert any(issue.check == "orphan-nodes" for issue in report.issues)


def test_health_counts_adaptive_updates(graph) -> None:
    learner, state, _ = learner_for(graph)
    learner.record_outcome(
        OutcomeRecord(cue="c", outcome=GOOD, path_edges=("e003",))
    )
    learner.record_outcome(
        OutcomeRecord(cue="c", outcome=BAD, path_edges=("e004",))
    )
    learner.decay_unused(used_edge_ids={"e004"})
    report = check_graph(graph, state)
    assert report.policy_version == state.policy_version
    assert report.strengthened == 1
    assert report.weakened == 1
    assert report.decayed >= 1
    assert "Association policy" in report.render()
