"""Scorer tests. A bug here is an instrument defect: it would create
false scientific conclusions, so every branch of the scorers is covered."""

import json

import pytest

from memory_measurement import (
    HistoryItem,
    MemoryObservation,
    MemoryTask,
    RunManifest,
    SystemOutput,
    render_scorecard,
    score_task,
)
from memory_measurement.controls import (
    STANDARD_CONDITIONS,
    memory_delta,
)
from memory_measurement.observations import FailureClass
from memory_measurement.scorers import (
    abstention_correctness,
    decision_exactness,
    source_precision,
    source_recall,
    supersession_correctness,
    temporal_accuracy,
    unsupported_source_rate,
)
from memory_measurement.tasks import DECISION, LOCATE, TEMPORAL, UNANSWERABLE


def locate_task() -> MemoryTask:
    return MemoryTask(
        task_id="t1",
        family=LOCATE,
        prompt="Where was X discussed?",
        history_ref="h",
        expected_sources=("s1", "s2"),
    )


def test_correct_answer_scores_full() -> None:
    task = locate_task()
    output = SystemOutput(
        task_id="t1",
        answer="s1 and s2",
        retrieved_ids=("s1", "s2"),
        cited_sources=("s1",),
    )
    observations = {o.metric: o for o in score_task(task, output, ("s1", "s2"))}
    assert observations["source_recall"].value == 1.0
    assert observations["source_precision"].value == 1.0
    assert observations["source_recall"].failure_class is None
    assert observations["abstention_correctness"].value is True


def test_wrong_answer_gets_interpretation_failure() -> None:
    task = MemoryTask(
        task_id="t2",
        family=DECISION,
        prompt="What was decided?",
        history_ref="h",
        expected_sources=("s1",),
        expected_state="PostgreSQL",
    )
    output = SystemOutput(
        task_id="t2", answer="Redis", retrieved_ids=("s1",)
    )
    observation = decision_exactness(task, output)
    assert observation is not None
    assert observation.value is False
    assert (
        observation.failure_class
        == FailureClass.CORRECT_EVIDENCE_WRONG_INTERPRETATION
    )


def test_superseded_answer_flagged() -> None:
    task = MemoryTask(
        task_id="t3",
        family=DECISION,
        prompt="What should new code target?",
        history_ref="h",
        expected_sources=("s1",),
        expected_state="PostgreSQL",
        superseded_options=("SQLite",),
    )
    output = SystemOutput(
        task_id="t3", answer="Use SQLite", retrieved_ids=("s1",)
    )
    decision = decision_exactness(task, output)
    assert decision is not None
    assert decision.failure_class == FailureClass.MISSED_SUPERSESSION
    supersession = supersession_correctness(task, output)
    assert supersession is not None
    assert supersession.value is False


def test_partial_evidence_recall() -> None:
    observation = source_recall(
        locate_task(),
        SystemOutput(task_id="t1", retrieved_ids=("s1",)),
    )
    assert observation.value == pytest.approx(0.5)
    assert observation.failure_class == FailureClass.CONTEXT_OMISSION


def test_extra_irrelevant_evidence_hurts_precision() -> None:
    observation = source_precision(
        locate_task(),
        SystemOutput(task_id="t1", retrieved_ids=("s1", "s2", "junk")),
    )
    assert observation.value == pytest.approx(2 / 3)
    assert observation.failure_class == FailureClass.CONTEXT_DISTRACTION


def test_stale_answer_to_current_question() -> None:
    task = MemoryTask(
        task_id="t4",
        family=TEMPORAL,
        prompt="What is true now?",
        history_ref="h",
        expected_sources=("s1",),
        temporal_mode="current",
        expected_current="PostgreSQL",
        expected_historical="SQLite",
    )
    observation = temporal_accuracy(
        task, SystemOutput(task_id="t4", answer="SQLite")
    )
    assert observation is not None
    assert observation.value is False
    assert observation.failure_class == FailureClass.STALE_STATE


def test_current_answer_to_historical_question_fails() -> None:
    task = MemoryTask(
        task_id="t5",
        family=TEMPORAL,
        prompt="What was true in March?",
        history_ref="h",
        expected_sources=("s1",),
        temporal_mode="historical",
        expected_current="PostgreSQL",
        expected_historical="SQLite",
    )
    observation = temporal_accuracy(
        task, SystemOutput(task_id="t5", answer="PostgreSQL")
    )
    assert observation is not None
    assert observation.value is False
    assert observation.failure_class == FailureClass.STALE_STATE


def test_historical_answer_scores() -> None:
    task = MemoryTask(
        task_id="t6",
        family=TEMPORAL,
        prompt="What was true in March?",
        history_ref="h",
        expected_sources=("s1",),
        temporal_mode="historical",
        expected_current="PostgreSQL",
        expected_historical="SQLite",
    )
    observation = temporal_accuracy(
        task, SystemOutput(task_id="t6", answer="SQLite in March")
    )
    assert observation is not None
    assert observation.value is True


def test_appropriate_abstention() -> None:
    task = MemoryTask(
        task_id="t7",
        family=DECISION,
        prompt="What cache was adopted?",
        history_ref="h",
        expected_sources=(),
        expected_status=UNANSWERABLE,
    )
    assert abstention_correctness(
        task, SystemOutput(task_id="t7", abstained=True)
    ).value is True
    assert (
        abstention_correctness(
            task, SystemOutput(task_id="t7", answer="Redis")
        ).failure_class
        == FailureClass.FAILED_ABSTENTION
    )


def test_inappropriate_abstention() -> None:
    observation = abstention_correctness(
        locate_task(), SystemOutput(task_id="t1", abstained=True)
    )
    assert observation.value is False
    assert observation.failure_class == FailureClass.UNNECESSARY_ABSTENTION


def test_empty_retrieval_flagged() -> None:
    observation = source_recall(
        locate_task(), SystemOutput(task_id="t1")
    )
    assert observation.value == 0.0
    assert observation.failure_class == FailureClass.NOT_RETRIEVED


def test_empty_expectation_empty_retrieval_is_fine() -> None:
    task = MemoryTask(
        task_id="t8",
        family=DECISION,
        prompt="What cache was adopted?",
        history_ref="h",
        expected_sources=(),
        expected_status=UNANSWERABLE,
    )
    observation = source_recall(task, SystemOutput(task_id="t8", abstained=True))
    assert observation.value == 1.0


def test_duplicate_evidence_deduped() -> None:
    observation = source_recall(
        locate_task(),
        SystemOutput(task_id="t1", retrieved_ids=("s1", "s1", "s2", "s2")),
    )
    assert observation.value == 1.0
    precision = source_precision(
        locate_task(),
        SystemOutput(task_id="t1", retrieved_ids=("s1", "s1", "s2")),
    )
    assert precision.value == 1.0
    assert any("duplicates" in e for e in precision.evidence)


def test_fabricated_source_detected() -> None:
    task = locate_task()
    observation = unsupported_source_rate(
        task,
        SystemOutput(task_id="t1", cited_sources=("s1", "ghost-9")),
        ("s1", "s2"),
    )
    assert observation is not None
    assert observation.value == pytest.approx(0.5)
    assert observation.failure_class == FailureClass.UNSUPPORTED_CLAIM


def test_no_citations_no_unsupported_claim() -> None:
    assert (
        unsupported_source_rate(
            locate_task(), SystemOutput(task_id="t1"), ("s1", "s2")
        )
        is None
    )


def test_task_output_mismatch_rejected() -> None:
    with pytest.raises(ValueError):
        score_task(locate_task(), SystemOutput(task_id="other"))


def test_memory_delta() -> None:
    assert memory_delta(0.8, 0.5) == pytest.approx(0.3)
    assert memory_delta(0.2, 0.9) < 0


def test_standard_conditions_cover_ladder() -> None:
    names = {c.name for c in STANDARD_CONDITIONS}
    assert {
        "no-memory",
        "lexical-retrieval",
        "embedding-top-k",
        "oracle-memory",
        "scrambled-history",
    } <= names


def test_manifest_round_trip_and_hash_stability() -> None:
    manifest = RunManifest(
        run_id="r1",
        system_name="s",
        condition="no-memory",
        corpus_version="c-v0.1",
        task_set_version="t-v0.1",
    )
    restored = RunManifest.from_dict(json.loads(manifest.to_json()))
    assert restored == manifest
    assert restored.manifest_hash == manifest.manifest_hash


def test_scorecard_labels_pending_and_failures() -> None:
    observations = [
        MemoryObservation(
            task_id="t1",
            metric="source_recall",
            value=0.5,
            failure_class=FailureClass.CONTEXT_OMISSION,
        )
    ]
    manifest = RunManifest(
        run_id="r1",
        system_name="s",
        condition="no-memory",
        corpus_version="c-v0.1",
        task_set_version="t-v0.1",
    )
    card = render_scorecard(observations, manifest)
    assert "pending" in card
    assert "CONTEXT_OMISSION" in card
    assert "Memory Measurement Run" in card


def test_expected_alias_accepted() -> None:
    task = MemoryTask(
        task_id="t9",
        family=DECISION,
        prompt="What was decided about the cache?",
        history_ref="h",
        expected_sources=("s1",),
        expected_state="will not introduce Redis",
        expected_aliases=("decided against redis", "no redis"),
    )
    observation = decision_exactness(
        task, SystemOutput(task_id="t9", answer="They decided against Redis.")
    )
    assert observation is not None
    assert observation.value is True


def test_negated_superseded_mention_is_not_violation() -> None:
    from memory_measurement.scorers import supersession_correctness

    task = MemoryTask(
        task_id="t10",
        family=DECISION,
        prompt="What about the cache?",
        history_ref="h",
        expected_sources=("s1",),
        expected_state="will not introduce Redis",
        superseded_options=("introduce Redis",),
    )
    observation = supersession_correctness(
        task,
        SystemOutput(
            task_id="t10",
            answer="The team decided not to introduce Redis.",
        ),
    )
    assert observation is not None
    assert observation.value is True
    assert observation.failure_class is None


def test_unnegated_superseded_use_is_violation() -> None:
    from memory_measurement.scorers import supersession_correctness

    task = MemoryTask(
        task_id="t11",
        family=DECISION,
        prompt="What should new code target?",
        history_ref="h",
        expected_sources=("s1",),
        expected_state="PostgreSQL",
        superseded_options=("SQLite",),
    )
    observation = supersession_correctness(
        task, SystemOutput(task_id="t11", answer="Use SQLite.")
    )
    assert observation is not None
    assert observation.value is False


def test_history_item_defaults() -> None:
    item = HistoryItem(item_id="x", text="words")
    assert item.kind == "record"
    assert item.timestamp is None
