"""Seeding, activation mechanics, and the four propagation strategies."""

from dataclasses import replace

import pytest

from associative_memory.activation.decay import (
    apply_threshold,
    exponential_time_decay,
    hop_decay,
    normalise,
)
from associative_memory.activation.inhibition import (
    competition_report,
    fan_divisor,
    lateral_inhibition,
)
from associative_memory.config import AssociativeConfig
from associative_memory.fixtures import build_cases, build_graph
from associative_memory.graph.adapter import (
    ENTITY,
    MemoryEdge,
    MemoryGraph,
    MemoryNode,
)
from associative_memory.pipeline import STRATEGIES, AssociativeMemory
from associative_memory.seeding.base import Seed, tokenise
from associative_memory.seeding.embedding import EmbeddingSeeder
from associative_memory.seeding.hybrid import HybridSeeder, OracleSeeder, build_seeder
from associative_memory.seeding.lexical import LexicalSeeder


@pytest.fixture(scope="module")
def graph():
    return build_graph()


@pytest.fixture(scope="module")
def cases():
    return {case.case_id: case for case in build_cases()}


# -- seeding ------------------------------------------------------------


def test_tokenise_keeps_identifiers_and_drops_stopwords() -> None:
    tokens = tokenise("What did we decide in adr-007 about the event-store?")
    assert "adr-007" in tokens
    assert "the" not in tokens and "did" not in tokens


def test_lexical_seeding_finds_the_named_artifact(graph) -> None:
    seeds = LexicalSeeder(top_k=5).seed("What does adr-009 record?", graph)
    assert "source:adr-009" in [seed.node_id for seed in seeds]
    assert all(seed.method == "lexical" for seed in seeds)


def test_seeding_respects_top_k_and_min_score(graph) -> None:
    seeds = LexicalSeeder(top_k=2, min_score=0.0).seed("PostgreSQL", graph)
    assert len(seeds) <= 2
    strict = LexicalSeeder(top_k=10, min_score=0.99).seed("PostgreSQL", graph)
    assert all(seed.score >= 0.99 for seed in strict)


def test_seeding_returns_nothing_for_an_empty_cue(graph) -> None:
    assert LexicalSeeder().seed("the and of", graph) == []


def test_embedding_seeding_is_deterministic(graph) -> None:
    seeder = EmbeddingSeeder(top_k=4)
    first = [s.node_id for s in seeder.seed("event store backend", graph)]
    second = [
        s.node_id for s in EmbeddingSeeder(top_k=4).seed("event store backend", graph)
    ]
    assert first == second


def test_hybrid_seeding_blends_both_components(graph) -> None:
    seeds = HybridSeeder(top_k=5).seed("Redis lookup cache", graph)
    assert seeds
    evidence = " ".join(seeds[0].evidence)
    assert "lexical=" in evidence and "embedding=" in evidence


def test_oracle_seeding_uses_supplied_nodes(graph) -> None:
    seeder = OracleSeeder({"cue": ["entity:event-store"]})
    seeds = seeder.seed("cue", graph)
    assert [s.node_id for s in seeds] == ["entity:event-store"]
    assert seeder.seed("unknown cue", graph) == []


def test_build_seeder_rejects_an_unknown_method() -> None:
    config = AssociativeConfig().seeding
    with pytest.raises(ValueError):
        build_seeder(replace(config, method="telepathy"))


# -- decay and competition ------------------------------------------------


def test_hop_decay_is_monotonic() -> None:
    values = [hop_decay(1.0, hop, 0.6) for hop in range(4)]
    assert values == sorted(values, reverse=True)
    assert values[0] == 1.0


def test_time_decay_weakens_with_the_gap() -> None:
    assert exponential_time_decay(1.0, 0.0) == pytest.approx(1.0)
    assert exponential_time_decay(1.0, 100.0) < exponential_time_decay(1.0, 10.0)


def test_normalise_peaks_at_one_and_preserves_order() -> None:
    normalised = normalise({"a": 2.0, "b": 1.0, "c": 0.0})
    assert max(normalised.values()) == 1.0
    assert normalised["a"] > normalised["b"] > normalised["c"]
    assert normalise({}) == {}
    assert normalise({"a": 0.0}) == {"a": 0.0}


def test_threshold_drops_weak_activation() -> None:
    assert apply_threshold({"a": 0.5, "b": 0.01}, 0.02) == {"a": 0.5}


def test_fan_divisor_penalises_hubs_only_when_enabled() -> None:
    assert fan_divisor(10, True) == 10.0
    assert fan_divisor(10, False) == 1.0
    assert fan_divisor(0, True) == 1.0


def test_lateral_inhibition_keeps_top_m_and_reports_what_it_removed() -> None:
    frontier = {"a": 1.0, "b": 0.8, "c": 0.6, "d": 0.4}
    kept, suppressed = lateral_inhibition(frontier, top_m=2, strength=0.5)
    assert kept["a"] == 1.0 and kept["b"] == 0.8
    assert kept["c"] == pytest.approx(0.3) and kept["d"] == pytest.approx(0.2)
    # Suppression is reported, not silently discarded.
    assert set(suppressed) == {"c", "d"}
    assert suppressed["c"] == pytest.approx(0.3)


def test_inhibition_is_a_no_op_when_disabled() -> None:
    frontier = {"a": 1.0, "b": 0.5}
    kept, suppressed = lateral_inhibition(frontier, top_m=0, strength=0.5)
    assert kept == frontier and suppressed == {}


def test_competition_report_describes_the_frontier() -> None:
    assert competition_report({}, 3)["frontier_size"] == 0.0
    report = competition_report({"a": 3.0, "b": 1.0}, 1)
    assert report["frontier_size"] == 2.0
    assert report["head_share"] == pytest.approx(0.75)


# -- propagation -----------------------------------------------------------


def cycle_graph() -> MemoryGraph:
    graph = MemoryGraph(version="cycle")
    for name in ("a", "b", "c"):
        graph.add_node(
            MemoryNode(node_id=name, kind=ENTITY, label=name, terms=(name,))
        )
    for edge_id, head, tail in (("ab", "a", "b"), ("bc", "b", "c"), ("ca", "c", "a")):
        graph.add_edge(
            MemoryEdge(
                edge_id=edge_id, source=head, target=tail, relation="R",
                association=0.9, source_ids=("s",),
            )
        )
    return graph


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_every_strategy_terminates_on_a_cycle(strategy) -> None:
    config = AssociativeConfig()
    memory = AssociativeMemory(
        graph=cycle_graph(), config=config, strategy=strategy
    )
    result = memory.retrieve("a")
    assert result.terminated_because
    assert result.steps_run <= max(
        config.propagation.max_hops, config.propagation.pagerank_iterations
    )
    assert len(result.admitted) <= config.selection.max_memories


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_every_strategy_respects_the_selection_budget(strategy, graph, cases) -> None:
    config = replace(
        AssociativeConfig(),
        selection=replace(AssociativeConfig().selection, max_memories=3),
    )
    memory = AssociativeMemory(graph=graph, config=config, strategy=strategy)
    result = memory.retrieve(cases["c-hop-why"].cue)
    assert len(result.admitted) <= 3
    assert len(result.explored) >= len(result.admitted)


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_every_strategy_records_provenance_for_admitted_memories(
    strategy, graph, cases
) -> None:
    memory = AssociativeMemory(
        graph=graph, config=AssociativeConfig(), strategy=strategy
    )
    result = memory.retrieve(cases["c-direct-target"].cue)
    for item in result.admitted:
        node = graph.nodes[item.node_id]
        assert item.source_ids == list(node.source_ids)
        assert item.path and item.path[-1] == item.node_id


def test_unknown_strategy_is_rejected(graph) -> None:
    with pytest.raises(ValueError):
        AssociativeMemory(
            graph=graph, config=AssociativeConfig(), strategy="telepathy"
        )


def test_hop_budget_binds(graph, cases) -> None:
    base = AssociativeConfig()
    shallow = replace(base, propagation=replace(base.propagation, max_hops=1))
    deep = replace(base, propagation=replace(base.propagation, max_hops=4))
    cue = cases["c-hop-backup"].cue
    near = AssociativeMemory(graph=graph, config=shallow,
                             strategy="spreading").retrieve(cue)
    far = AssociativeMemory(graph=graph, config=deep,
                            strategy="spreading").retrieve(cue)
    assert near.steps_run == 1
    assert far.steps_run == 4
    # More hops means more of the graph touched and more edges walked...
    assert far.nodes_expanded >= near.nodes_expanded
    assert far.edges_traversed > near.edges_traversed
    # ...but not a larger surviving set: decay culls nodes that stop
    # receiving activation, so deeper propagation concentrates rather than
    # accumulates. This is the behaviour the threshold exists to produce.
    assert len(far.explored) <= far.nodes_expanded


def test_decay_culls_the_surviving_set_as_propagation_deepens(graph, cases) -> None:
    base = AssociativeConfig()
    cue = cases["c-hop-backup"].cue
    survivors = []
    for hops in (1, 2, 3, 4):
        result = AssociativeMemory(
            graph=graph,
            config=replace(base, propagation=replace(base.propagation,
                                                     max_hops=hops)),
            strategy="spreading",
        ).retrieve(cue)
        survivors.append(len(result.explored))
    # Without decay the set would only grow. With it, deep propagation can
    # end with fewer active memories than shallow propagation did.
    assert min(survivors) < max(survivors)
    assert survivors[-1] <= survivors[0]


def test_node_budget_binds(graph, cases) -> None:
    base = AssociativeConfig()
    config = replace(
        base,
        propagation=replace(
            base.propagation,
            max_nodes_expanded=8,
            activation_threshold=0.0,
            max_hops=5,
        ),
    )
    result = AssociativeMemory(
        graph=graph, config=config, strategy="spreading"
    ).retrieve(cases["c-hop-why"].cue)
    assert result.terminated_because == "node-budget"


def test_threshold_bounds_expansion(graph, cases) -> None:
    base = AssociativeConfig()
    cue = cases["c-hop-why"].cue
    tight = AssociativeMemory(graph=graph, config=base,
                              strategy="spreading").retrieve(cue)
    loose = AssociativeMemory(
        graph=graph,
        config=replace(
            base, propagation=replace(base.propagation, activation_threshold=0.0)
        ),
        strategy="spreading",
    ).retrieve(cue)
    assert len(loose.explored) > len(tight.explored)


def test_fan_division_reduces_hub_transmission(graph, cases) -> None:
    base = AssociativeConfig()
    cue = cases["c-adv-hub"].cue
    with_fan = AssociativeMemory(graph=graph, config=base,
                                 strategy="spreading").retrieve(cue)
    without = AssociativeMemory(
        graph=graph,
        config=replace(
            base, propagation=replace(base.propagation, fan_division=False)
        ),
        strategy="spreading",
    ).retrieve(cue)
    assert len(without.explored) >= len(with_fan.explored)


def test_propagation_reaches_beyond_the_seeds(graph, cases) -> None:
    memory = AssociativeMemory(
        graph=graph, config=AssociativeConfig(), strategy="spreading"
    )
    result = memory.retrieve(cases["c-hop-backup"].cue)
    seeded = {seed.node_id for seed in result.seeds}
    reached = {item.node_id for item in result.explored}
    assert reached - seeded, "propagation added nothing to seeding"
    assert max(item.hops for item in result.explored) >= 1


def test_cue_conditioning_changes_edge_weights(graph) -> None:
    from associative_memory.propagation.conditioned import CueConditionedWeights

    weights = CueConditionedWeights(strength=1.0, floor=0.1)
    edge = next(e for e in graph.edges if e.edge_id == "e070")  # partner facade
    on_topic = weights("What preserves the partner facade commitment?", edge)
    off_topic = weights("Which importer throughput baseline is current?", edge)
    assert on_topic > off_topic
    # Conditioning attenuates; it never severs, so the graph itself stays
    # independent of the query.
    assert off_topic > 0.0


def test_conditioning_strength_zero_reduces_to_plain_association(graph) -> None:
    from associative_memory.propagation.conditioned import CueConditionedWeights

    weights = CueConditionedWeights(strength=0.0)
    edge = graph.edges[0]
    assert weights("anything at all", edge) == edge.association


def test_same_entity_different_cue_activates_different_regions(graph, cases) -> None:
    """The chapter's central claim, as an executable assertion."""
    memory = AssociativeMemory(
        graph=graph, config=AssociativeConfig(), strategy="conditioned"
    )
    backend = memory.retrieve(cases["c-cond-silva-eventstore"].cue)
    corpus = memory.retrieve(cases["c-cond-silva-corpus"].cue)
    orphans = memory.retrieve(cases["c-cond-silva-orphans"].cue)
    admitted = [
        set(result.admitted_sources())
        for result in (backend, corpus, orphans)
    ]
    assert "session-031" in admitted[0]
    assert "issue-088" in admitted[1]
    assert "incident-034" in admitted[2]
    # Each cue must reach its own branch and not collapse into one region.
    assert admitted[0] != admitted[1] != admitted[2]


def test_pagerank_converges_and_reports_its_approximation(graph, cases) -> None:
    result = AssociativeMemory(
        graph=graph, config=AssociativeConfig(), strategy="pagerank"
    ).retrieve(cases["c-direct-target"].cue)
    assert result.terminated_because in ("converged", "iteration-budget")
    assert "approximate" in result.notes


def test_pagerank_without_seeds_returns_nothing(graph) -> None:
    from associative_memory.propagation.pagerank import (
        PersonalizedPageRankRetriever,
    )

    config = AssociativeConfig()
    retriever = PersonalizedPageRankRetriever(
        config.propagation, config.selection
    )
    result = retriever.retrieve("cue", graph, [])
    assert result.admitted == []
    assert result.terminated_because == "no-seeds"


def test_result_serialises_with_its_costs(graph, cases) -> None:
    result = AssociativeMemory(
        graph=graph, config=AssociativeConfig(), strategy="spreading"
    ).retrieve(cases["c-hop-why"].cue)
    payload = result.to_dict()
    for key in (
        "strategy", "seeds", "admitted", "explored_count", "nodes_expanded",
        "edges_traversed", "expansion_factor", "latency_ms",
        "activation_concentration", "terminated_because",
    ):
        assert key in payload


def test_expansion_factor_with_nothing_admitted() -> None:
    from associative_memory.propagation.base import RetrievalResult

    assert RetrievalResult(cue="c", strategy="s").expansion_factor() == 0.0


def test_seed_score_alone_does_not_decide_admission(graph, cases) -> None:
    """Selection fuses activation with similarity; weights are explicit."""
    base = AssociativeConfig()
    activation_only = replace(
        base,
        selection=replace(
            base.selection,
            activation_weight=1.0,
            similarity_weight=0.0,
            importance_weight=0.0,
        ),
    )
    cue = cases["c-hop-backup"].cue
    fused = AssociativeMemory(graph=graph, config=base,
                              strategy="spreading").retrieve(cue)
    pure = AssociativeMemory(graph=graph, config=activation_only,
                             strategy="spreading").retrieve(cue)
    assert [m.node_id for m in fused.admitted] != [
        m.node_id for m in pure.admitted
    ]
