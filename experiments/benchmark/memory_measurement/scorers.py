"""Deterministic (mechanical) scorers.

These scorers use only string comparison and set arithmetic over ledger
identifiers. Anything requiring judgement — paraphrase equivalence,
rationale quality, calibration — belongs to a versioned model or human
grader, recorded in the run manifest, never blurred into these scores.

Conventions:
- Source identifiers are deduplicated before scoring; duplication is
  reported in the observation evidence rather than punished twice.
- Empty retrieval against a non-empty expectation scores 0.0 with
  NOT_RETRIEVED. Empty retrieval against an empty expectation scores 1.0:
  the ledger requires nothing, and nothing was fetched.
- A bug in a scorer is an instrument defect, not a software defect. Every
  branch below has a corresponding test in ``tests/test_scorers.py``.
"""

from __future__ import annotations

import re

from .observations import FailureClass, MemoryObservation
from .tasks import ANSWERABLE, MemoryTask, SystemOutput, UNANSWERABLE

from ._version import __version__



def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _dedupe(ids: tuple[str, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for item in ids:
        if item not in seen:
            seen.append(item)
    return tuple(seen)


def _states_match(expected: str, answer: str) -> bool:
    return _normalize(expected) in _normalize(answer)


# Tokens suggesting a superseded option is mentioned to reject it,
# not to recommend it. A match inside such a window is not a
# supersession violation. Documented limitation: scope errors remain
# possible ("not X, but Y" is handled; irony is not).
_NEGATION_TOKENS = (
    "not", "n't", "never", "no", "without", "reject", "rejected",
    "rejects", "against", "instead", "declined", "refused", "abandoned",
    "ruled out",
)


def _match_negated(answer_normalised: str, match_at: int) -> bool:
    window = answer_normalised[max(0, match_at - 60) : match_at]
    return any(token in window.split() for token in _NEGATION_TOKENS)


def _any_state_matches(
    candidates: tuple[str | None, ...], answer: str
) -> str | None:
    """First candidate whose normalised form appears in the answer."""
    for candidate in candidates:
        if candidate is not None and _states_match(candidate, answer):
            return candidate
    return None


def source_recall(
    task: MemoryTask, output: SystemOutput
) -> MemoryObservation:
    """What fraction of the ledger's required evidence was retrieved?"""
    expected = _dedupe(task.expected_sources)
    retrieved = _dedupe(output.retrieved_ids)
    if not expected:
        return MemoryObservation(
            task_id=task.task_id,
            metric="source_recall",
            value=1.0,
            evidence=(),
            notes="ledger requires no sources",
        )
    if not retrieved:
        return MemoryObservation(
            task_id=task.task_id,
            metric="source_recall",
            value=0.0,
            evidence=tuple(f"missing:{source}" for source in expected),
            failure_class=FailureClass.NOT_RETRIEVED,
        )
    hit = [s for s in expected if s in retrieved]
    missing = [s for s in expected if s not in retrieved]
    value = len(hit) / len(expected)
    return MemoryObservation(
        task_id=task.task_id,
        metric="source_recall",
        value=value,
        evidence=tuple([f"hit:{s}" for s in hit] + [f"missing:{s}" for s in missing]),
        failure_class=(
            FailureClass.CONTEXT_OMISSION if missing else None
        ),
    )


def source_precision(
    task: MemoryTask, output: SystemOutput
) -> MemoryObservation:
    """What fraction of the retrieved material was ledger-relevant?"""
    expected = set(task.expected_sources)
    retrieved = _dedupe(output.retrieved_ids)
    duplicates = len(output.retrieved_ids) - len(retrieved)
    if not retrieved:
        return MemoryObservation(
            task_id=task.task_id,
            metric="source_precision",
            value=1.0 if not expected else 0.0,
            evidence=("empty-retrieval",),
            failure_class=(
                None if not expected else FailureClass.NOT_RETRIEVED
            ),
        )
    relevant = [s for s in retrieved if s in expected]
    irrelevant = [s for s in retrieved if s not in expected]
    value = len(relevant) / len(retrieved)
    evidence = tuple(
        [f"relevant:{s}" for s in relevant]
        + [f"irrelevant:{s}" for s in irrelevant]
        + ([f"duplicates:{duplicates}"] if duplicates else [])
    )
    return MemoryObservation(
        task_id=task.task_id,
        metric="source_precision",
        value=value,
        evidence=evidence,
        failure_class=(
            FailureClass.CONTEXT_DISTRACTION if irrelevant else None
        ),
    )


def decision_exactness(
    task: MemoryTask, output: SystemOutput
) -> MemoryObservation | None:
    """Does the answer name the decision the ledger records?"""
    if task.expected_state is None:
        return None
    if output.abstained or not output.answer:
        return MemoryObservation(
            task_id=task.task_id,
            metric="decision_exactness",
            value=False,
            evidence=("abstained-or-empty",),
            failure_class=FailureClass.UNNECESSARY_ABSTENTION
            if output.abstained
            else FailureClass.CORRECT_MEMORY_NOT_USED,
        )
    if _any_state_matches(
        (task.expected_state, *task.expected_aliases), output.answer
    ) is not None:
        return MemoryObservation(
            task_id=task.task_id,
            metric="decision_exactness",
            value=True,
            evidence=(f"matched:{task.expected_state}",),
        )
    failure = FailureClass.CORRECT_EVIDENCE_WRONG_INTERPRETATION
    for option in task.superseded_options:
        if _states_match(option, output.answer):
            failure = FailureClass.MISSED_SUPERSESSION
            break
    return MemoryObservation(
        task_id=task.task_id,
        metric="decision_exactness",
        value=False,
        evidence=(f"expected:{task.expected_state}",),
        failure_class=failure,
    )


def temporal_accuracy(
    task: MemoryTask, output: SystemOutput
) -> MemoryObservation | None:
    """Current-state and historical-state questions score separately.

    A historically accurate answer to a current-state question is a
    failure (STALE_STATE), not a partial success — and symmetrically for
    the historical direction.
    """
    if task.temporal_mode is None:
        return None
    metric = (
        "current_state_accuracy"
        if task.temporal_mode == "current"
        else "historical_state_accuracy"
    )
    if output.abstained or not output.answer:
        return MemoryObservation(
            task_id=task.task_id,
            metric=metric,
            value=False,
            evidence=("abstained-or-empty",),
            failure_class=FailureClass.UNNECESSARY_ABSTENTION
            if output.abstained
            else FailureClass.CORRECT_MEMORY_NOT_USED,
        )
    wanted = (
        task.expected_current
        if task.temporal_mode == "current"
        else task.expected_historical
    )
    other = (
        task.expected_historical
        if task.temporal_mode == "current"
        else task.expected_current
    )
    if _any_state_matches(
        (wanted, *task.expected_aliases), output.answer
    ) is not None:
        return MemoryObservation(
            task_id=task.task_id,
            metric=metric,
            value=True,
            evidence=(f"matched:{wanted}",),
        )
    if other is not None and _states_match(other, output.answer):
        return MemoryObservation(
            task_id=task.task_id,
            metric=metric,
            value=False,
            evidence=(f"answered-other-interval:{other}",),
            failure_class=FailureClass.STALE_STATE,
        )
    return MemoryObservation(
        task_id=task.task_id,
        metric=metric,
        value=False,
        evidence=(f"expected:{wanted}",),
        failure_class=FailureClass.STALE_STATE
        if task.temporal_mode == "current"
        else FailureClass.CORRECT_EVIDENCE_WRONG_INTERPRETATION,
    )


def supersession_correctness(
    task: MemoryTask, output: SystemOutput
) -> MemoryObservation | None:
    """Does the answer avoid recommending a superseded option?"""
    if not task.superseded_options or not output.answer or output.abstained:
        return None
    normalised = _normalize(output.answer)
    violated = []
    for option in task.superseded_options:
        at = normalised.find(_normalize(option))
        if at >= 0 and not _match_negated(normalised, at):
            violated.append(option)
    return MemoryObservation(
        task_id=task.task_id,
        metric="supersession_correctness",
        value=not violated,
        evidence=tuple(f"used-superseded:{o}" for o in violated) or ("no-superseded-use",),
        failure_class=FailureClass.MISSED_SUPERSESSION if violated else None,
    )


def abstention_correctness(
    task: MemoryTask, output: SystemOutput
) -> MemoryObservation:
    """When history does not determine an answer, refusing is correct."""
    if task.expected_status == UNANSWERABLE:
        return MemoryObservation(
            task_id=task.task_id,
            metric="abstention_correctness",
            value=output.abstained,
            evidence=("abstained",) if output.abstained else ("answered-unanswerable",),
            failure_class=None
            if output.abstained
            else FailureClass.FAILED_ABSTENTION,
        )
    return MemoryObservation(
        task_id=task.task_id,
        metric="abstention_correctness",
        value=not output.abstained,
        evidence=("answered",) if not output.abstained else ("abstained-on-answerable",),
        failure_class=FailureClass.UNNECESSARY_ABSTENTION
        if output.abstained
        else None,
    )


def unsupported_source_rate(
    task: MemoryTask,
    output: SystemOutput,
    history_ids: tuple[str, ...],
) -> MemoryObservation | None:
    """Do cited sources exist anywhere in the available history?

    Citing a source identifier that appears in no history artifact is
    fabrication, whether or not the answer text happens to be right.
    """
    cited = _dedupe(output.cited_sources)
    if not cited:
        return None
    known = set(history_ids)
    fabricated = [c for c in cited if c not in known]
    value = len(fabricated) / len(cited)
    return MemoryObservation(
        task_id=task.task_id,
        metric="unsupported_source_rate",
        value=value,
        evidence=tuple([f"fabricated:{c}" for c in fabricated] or ["all-cited-known"]),
        failure_class=(
            FailureClass.UNSUPPORTED_CLAIM if fabricated else None
        ),
    )


def score_task(
    task: MemoryTask,
    output: SystemOutput,
    history_ids: tuple[str, ...] = (),
) -> list[MemoryObservation]:
    """Run every applicable mechanical scorer for one task output."""
    if task.task_id != output.task_id:
        raise ValueError(
            f"task/output mismatch: {task.task_id} vs {output.task_id}"
        )
    observations: list[MemoryObservation] = [
        source_recall(task, output),
        source_precision(task, output),
        abstention_correctness(task, output),
    ]
    for observation in (
        decision_exactness(task, output),
        temporal_accuracy(task, output),
        supersession_correctness(task, output),
        unsupported_source_rate(task, output, history_ids),
    ):
        if observation is not None:
            observations.append(observation)
    return observations
