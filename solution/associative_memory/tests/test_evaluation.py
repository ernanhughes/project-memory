"""Instrument adapter, path-quality metrics, and the experiment suite."""

import pytest

from associative_memory.config import AssociativeConfig
from associative_memory.evaluation.adapter import (
    AssociativeCase,
    metric_means,
    score_case,
    to_system_output,
)
from associative_memory.experiments import (
    EXPERIMENTS,
    _seed_only_result,
    run_condition,
    run_suite,
)
from associative_memory.fixtures import build_cases, build_graph
from associative_memory.pipeline import AssociativeMemory


@pytest.fixture(scope="module")
def graph():
    return build_graph()


@pytest.fixture(scope="module")
def cases():
    return build_cases()


@pytest.fixture(scope="module")
def by_id(cases):
    return {case.case_id: case for case in cases}


def run(graph, case, strategy="spreading", config=None):
    memory = AssociativeMemory(
        graph=graph, config=config or AssociativeConfig(), strategy=strategy
    )
    return memory.retrieve(case.cue)


# -- adapter -------------------------------------------------------------


def test_case_converts_to_an_instrument_task(by_id) -> None:
    task = by_id["c-hop-why"].as_memory_task()
    assert task.task_id == "c-hop-why"
    assert task.expected_sources
    assert task.expected_status == "answerable"


def test_system_output_reports_retrieval_not_an_answer(graph, by_id) -> None:
    case = by_id["c-direct-target"]
    output = to_system_output(case, run(graph, case))
    assert output.answer is None
    assert output.cited_sources == ()
    assert output.retrieved_ids
    assert output.context_tokens is not None


def test_empty_retrieval_counts_as_abstention() -> None:
    from associative_memory.propagation.base import RetrievalResult

    case = AssociativeCase(case_id="x", cue="c", family="locate")
    output = to_system_output(case, RetrievalResult(cue="c", strategy="s"))
    assert output.abstained is True


def test_score_case_produces_instrument_and_path_metrics(graph, by_id) -> None:
    case = by_id["c-hop-why"]
    scored = score_case(case, run(graph, case), graph, "spreading")
    metrics = {o["metric"] for o in scored.observations}
    # Chapter 2 owns these.
    assert {"source_recall", "source_precision", "abstention_correctness"} <= metrics
    # Chapter 5 adds these, kept separate.
    assert {
        "path_recall",
        "path_precision",
        "expansion_factor",
        "useful_hop_distance",
        "activation_concentration",
        "hub_capture",
    } <= metrics
    assert scored.paths and scored.seeds


def test_distractor_metric_only_appears_when_the_fixture_labels_traps(
    graph, by_id
) -> None:
    labelled = score_case(
        by_id["c-adv-echo"], run(graph, by_id["c-adv-echo"]), graph, "s"
    )
    assert any(o["metric"] == "distractor_rate" for o in labelled.observations)
    plain = AssociativeCase(
        case_id="p", cue="PostgreSQL", family="locate",
        expected_sources=("adr-007",),
    )
    scored = score_case(plain, run(graph, plain), graph, "s")
    assert not any(o["metric"] == "distractor_rate" for o in scored.observations)


def test_path_recall_can_exceed_source_recall(graph, by_id) -> None:
    """The diagnostic that separates a traversal failure from a selection one."""
    case = by_id["c-hop-backup"]
    scored = score_case(case, run(graph, case), graph, "spreading")
    values = {o["metric"]: o["value"] for o in scored.observations}
    assert values["path_recall"] >= values["source_recall"]


def test_useful_hop_distance_is_none_when_evidence_is_never_reached(graph) -> None:
    case = AssociativeCase(
        case_id="unreachable",
        cue="Redis lookup cache",
        family="locate",
        expected_sources=("platform-note-125",),
    )
    scored = score_case(case, run(graph, case), graph, "spreading")
    values = {o["metric"]: o["value"] for o in scored.observations}
    assert values["useful_hop_distance"] is None
    assert values["path_recall"] == 0.0


def test_seed_only_floor_does_no_propagation(graph, by_id) -> None:
    memory = AssociativeMemory(
        graph=graph, config=AssociativeConfig(), strategy="spreading"
    )
    result = _seed_only_result(memory, by_id["c-hop-backup"].cue)
    assert result.edges_traversed == 0
    assert result.steps_run == 0
    assert result.terminated_because == "no-propagation"
    assert all(item.hops == 0 for item in result.admitted)
    assert result.expansion_factor() == pytest.approx(1.0)


def test_metric_means_skips_missing_values(graph, by_id) -> None:
    case = by_id["c-hop-why"]
    scored = [score_case(case, run(graph, case), graph, "spreading")]
    means = metric_means(scored)
    assert means["source_recall"] is not None
    assert all(
        isinstance(value, float) for value in means.values() if value is not None
    )


def test_run_condition_reports_cost_alongside_quality(graph, cases) -> None:
    _scored, summary, _runs = run_condition(
        "spreading", graph, AssociativeConfig(), "spreading", cases
    )
    for key in (
        "means", "total_nodes_expanded", "total_edges_traversed",
        "mean_context_tokens", "mean_latency_ms", "manifest",
    ):
        assert key in summary
    assert summary["manifest"]["strategy"] == "spreading"
    assert summary["manifest"]["graph_version"] == graph.version


def test_context_budget_is_matched_across_strategies(graph, cases) -> None:
    """No strategy may win by admitting more memories than another."""
    limits = []
    for strategy in ("direct", "pagerank", "spreading", "conditioned"):
        _scored, _summary, runs = run_condition(
            strategy, graph, AssociativeConfig(), strategy, cases
        )
        limits.append(max(len(result.admitted) for _case, result in runs))
    assert all(limit <= AssociativeConfig().selection.max_memories
               for limit in limits)


# -- suite -----------------------------------------------------------------


def test_suite_runs_and_labels_its_limitation() -> None:
    report = run_suite(only=("E5-A",))
    assert report["suite_version"]
    assert "Retrieval-level only" in report["limitation"]
    assert "graph_health" in report and "config" in report
    assert set(report["experiments"]) == {"E5-A"}


def test_every_named_experiment_runs() -> None:
    report = run_suite()
    assert set(report["experiments"]) == set(EXPERIMENTS)
    for name, result in report["experiments"].items():
        assert result["experiment"] == name
        assert result["question"]


def test_shuffle_control_is_weaker_than_the_real_graph() -> None:
    """If a rewired graph scored the same, the edges carried no information."""
    report = run_suite(only=("E5-A",))
    conditions = report["experiments"]["E5-A"]["conditions"]
    real = conditions["spreading"]["means"]["source_recall"]
    shuffled = conditions["spreading-shuffled-control"]["means"]["source_recall"]
    assert real > shuffled


def test_e5g_adaptive_state_is_replayable_and_rollbackable() -> None:
    report = run_suite(only=("E5-G",))
    result = report["experiments"]["E5-G"]
    assert result["replay_reproduces_weights"] is True
    assert result["rollback_reproduces_base"] is True
    assert result["updates_recorded"] > 0


def test_e5h_frequency_policy_runs_away_and_outcome_policy_does_not() -> None:
    report = run_suite(only=("E5-H",))
    policies = report["experiments"]["E5-H"]["policies"]
    start = policies["frequency-only"]["initial_false_edge_weight"]
    assert policies["frequency-only"]["final_false_edge_weight"] > start
    assert policies["outcome-gated"]["final_false_edge_weight"] < start
    assert "frequency-reinforcement" in policies["frequency-only"]["health_flags"]
    assert (
        "frequency-reinforcement"
        not in policies["outcome-gated"]["health_flags"]
    )


def test_e5f_false_edge_is_detectable_by_health(graph) -> None:
    report = run_suite(only=("E5-F",))
    result = report["experiments"]["E5-F"]
    assert result["health_flags_it"] is True
    assert "clean" in result["affected_case"]
    assert "false-edge" in result["affected_case"]
