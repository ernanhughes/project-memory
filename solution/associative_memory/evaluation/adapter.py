"""Adapter between associative retrieval and the Measurement Instrument.

Chapter 2 owns scoring. Nothing here reimplements a scorer: an
associative retrieval is converted into the instrument's ``SystemOutput``
and handed to ``score_task`` exactly as the Chapter 3 baseline is.

What this module *does* add is a small set of path-quality observations
that only make sense for a system that traverses. They are diagnostic —
they explain where a recall or precision number came from — and they are
kept separate from the instrument's metrics rather than blended into
them. If they turn out not to explain anything, they are dropped without
touching the scored result.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
INSTRUMENT_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark"
for candidate in (str(SOLUTION_ROOT), str(INSTRUMENT_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from memory_measurement.observations import (  # noqa: E402
    FailureClass,
    MemoryObservation,
)
from memory_measurement.tasks import MemoryTask, SystemOutput  # noqa: E402


@dataclass
class AssociativeCase:
    """One cue run through one configuration, with its ground truth."""

    case_id: str
    cue: str
    family: str
    expected_sources: tuple[str, ...] = ()
    expected_path: tuple[str, ...] = ()
    distractor_sources: tuple[str, ...] = ()
    hop_class: str = "direct"  # direct | indirect | adversarial | unanswerable
    expected_status: str = "answerable"
    notes: str = ""

    def as_memory_task(self) -> MemoryTask:
        return MemoryTask(
            task_id=self.case_id,
            family=self.family,
            prompt=self.cue,
            history_ref="assoc-fixture-v0.1",
            expected_sources=self.expected_sources,
            expected_status=self.expected_status,
            notes=self.notes,
        )


def to_system_output(case: AssociativeCase, result) -> SystemOutput:
    """Retrieval-level output: what the memory layer handed forward.

    No reader runs in these experiments, so ``answer`` is None and the
    scored quantities are the retrieval ones. Answer correctness enters
    only when the same selection is passed to the Chapter 3 reader under
    a matched context budget.
    """
    return SystemOutput(
        task_id=case.case_id,
        answer=None,
        cited_sources=(),
        retrieved_ids=tuple(result.admitted_sources()),
        abstained=not result.admitted,
        context_tokens=estimate_context_tokens(result),
    )


def estimate_context_tokens(result) -> int:
    """Rough token cost of the admitted selection.

    The same four-characters-per-token estimate the Chapter 4 adapter
    uses, so the two chapters' context-cost columns are comparable.
    """
    characters = 0
    for memory in result.admitted:
        characters += len(memory.label) + 1
        characters += sum(len(source) + 2 for source in memory.source_ids)
    return max(0, characters // 4)


# -- path-quality observations -----------------------------------------


def path_recall(case: AssociativeCase, result) -> MemoryObservation:
    """Did any activated path reach the evidence the ledger requires?

    Distinct from source recall: this asks about everything propagation
    *touched*, not only what survived the selection budget. A case where
    path recall is high and source recall is low is a selection failure;
    the reverse is a traversal failure. Naming which one is the point.
    """
    expected = set(case.expected_sources)
    if not expected:
        return MemoryObservation(
            task_id=case.case_id,
            metric="path_recall",
            value=1.0,
            notes="ledger requires no sources",
        )
    reached = set(result.explored_sources())
    hit = expected & reached
    return MemoryObservation(
        task_id=case.case_id,
        metric="path_recall",
        value=len(hit) / len(expected),
        evidence=tuple(
            [f"reached:{s}" for s in sorted(hit)]
            + [f"unreached:{s}" for s in sorted(expected - reached)]
        ),
        failure_class=(
            None if hit == expected else FailureClass.NOT_RETRIEVED
        ),
    )


def path_precision(case: AssociativeCase, result) -> MemoryObservation:
    """How much of what propagation activated was ledger-relevant?"""
    expected = set(case.expected_sources)
    reached = result.explored_sources()
    if not reached:
        return MemoryObservation(
            task_id=case.case_id,
            metric="path_precision",
            value=1.0 if not expected else 0.0,
            evidence=("nothing-activated",),
        )
    relevant = [s for s in reached if s in expected]
    return MemoryObservation(
        task_id=case.case_id,
        metric="path_precision",
        value=len(relevant) / len(reached),
        evidence=(f"relevant={len(relevant)}", f"activated={len(reached)}"),
        failure_class=(
            FailureClass.CONTEXT_DISTRACTION
            if len(relevant) < len(reached)
            else None
        ),
    )


def expansion_factor(case: AssociativeCase, result) -> MemoryObservation:
    """Memories activated per memory admitted. Lower is cheaper."""
    return MemoryObservation(
        task_id=case.case_id,
        metric="expansion_factor",
        value=result.expansion_factor(),
        evidence=(
            f"explored={len(result.explored)}",
            f"admitted={len(result.admitted)}",
        ),
    )


def useful_hop_distance(case: AssociativeCase, result) -> MemoryObservation:
    """How many hops it took to reach the required evidence."""
    expected = set(case.expected_sources)
    if not expected:
        return MemoryObservation(
            task_id=case.case_id, metric="useful_hop_distance", value=0.0
        )
    distances = [
        memory.hops
        for memory in result.explored
        if expected & set(memory.source_ids)
    ]
    if not distances:
        return MemoryObservation(
            task_id=case.case_id,
            metric="useful_hop_distance",
            value=None,
            evidence=("evidence-never-reached",),
            failure_class=FailureClass.NOT_RETRIEVED,
        )
    return MemoryObservation(
        task_id=case.case_id,
        metric="useful_hop_distance",
        value=float(max(distances)),
        evidence=(f"min={min(distances)}", f"max={max(distances)}"),
    )


def activation_concentration(
    case: AssociativeCase, result
) -> MemoryObservation:
    """Share of activation held by the strongest few memories."""
    value = result.state.concentration() if result.state else 0.0
    return MemoryObservation(
        task_id=case.case_id,
        metric="activation_concentration",
        value=value,
        evidence=(f"terminated={result.terminated_because}",),
    )


def distractor_propagation(
    case: AssociativeCase, result
) -> MemoryObservation | None:
    """Did a known distractor accumulate enough activation to be admitted?

    Fixtures label their traps — echoes, tempting branches, popular hubs
    on the wrong route. Scoring against those labels is what stops the
    chapter from claiming hub resistance it never tested.
    """
    if not case.distractor_sources:
        return None
    admitted = set(result.admitted_sources())
    caught = [s for s in case.distractor_sources if s in admitted]
    return MemoryObservation(
        task_id=case.case_id,
        metric="distractor_rate",
        value=len(caught) / len(case.distractor_sources),
        evidence=tuple(f"admitted-distractor:{s}" for s in caught)
        or ("no-distractors-admitted",),
        failure_class=FailureClass.CONTEXT_DISTRACTION if caught else None,
    )


def hub_capture(case: AssociativeCase, result, graph) -> MemoryObservation:
    """Fraction of admitted memories that are among the graph's top hubs.

    High hub capture with low source recall is the cognitive-tunnelling
    failure the SYNAPSE authors report: inhibition concentrating recall
    on the loudest node rather than the right one.
    """
    hub_ids = {node_id for node_id, _ in graph.hubs(top=5)}
    if not result.admitted:
        return MemoryObservation(
            task_id=case.case_id, metric="hub_capture", value=0.0,
            evidence=("nothing-admitted",),
        )
    captured = [m.node_id for m in result.admitted if m.node_id in hub_ids]
    return MemoryObservation(
        task_id=case.case_id,
        metric="hub_capture",
        value=len(captured) / len(result.admitted),
        evidence=tuple(f"hub:{node_id}" for node_id in captured)
        or ("no-hubs-admitted",),
    )


@dataclass
class CaseResult:
    case_id: str
    condition: str
    observations: list[dict] = field(default_factory=list)
    admitted_sources: list[str] = field(default_factory=list)
    explored_sources: list[str] = field(default_factory=list)
    seeds: list[dict] = field(default_factory=list)
    paths: list[dict] = field(default_factory=list)
    nodes_expanded: int = 0
    edges_traversed: int = 0
    context_tokens_estimate: int = 0
    latency_ms: float = 0.0
    terminated_because: str = ""

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "condition": self.condition,
            "observations": self.observations,
            "admitted_sources": self.admitted_sources,
            "explored_sources": self.explored_sources,
            "seeds": self.seeds,
            "paths": self.paths,
            "nodes_expanded": self.nodes_expanded,
            "edges_traversed": self.edges_traversed,
            "context_tokens_estimate": self.context_tokens_estimate,
            "latency_ms": round(self.latency_ms, 3),
            "terminated_because": self.terminated_because,
        }


def score_case(case: AssociativeCase, result, graph, condition: str) -> CaseResult:
    """Instrument metrics plus path diagnostics for one cue under one system."""
    from memory_measurement.scorers import score_task

    task = case.as_memory_task()
    output = to_system_output(case, result)
    observations = list(score_task(task, output, case.expected_sources))
    for extra in (
        path_recall(case, result),
        path_precision(case, result),
        expansion_factor(case, result),
        useful_hop_distance(case, result),
        activation_concentration(case, result),
        distractor_propagation(case, result),
        hub_capture(case, result, graph),
    ):
        if extra is not None:
            observations.append(extra)
    return CaseResult(
        case_id=case.case_id,
        condition=condition,
        observations=[
            {
                "metric": o.metric,
                "value": o.value,
                "failure_class": o.failure_class,
                "evidence": list(o.evidence),
                "grader": o.grader,
            }
            for o in observations
        ],
        admitted_sources=result.admitted_sources(),
        explored_sources=result.explored_sources(),
        seeds=[seed.to_dict() for seed in result.seeds],
        paths=[memory.to_dict() for memory in result.admitted],
        nodes_expanded=result.nodes_expanded,
        edges_traversed=result.edges_traversed,
        context_tokens_estimate=output.context_tokens or 0,
        latency_ms=result.latency_ms,
        terminated_because=result.terminated_because,
    )


def metric_means(cases: list[CaseResult]) -> dict[str, float | None]:
    by_metric: dict[str, list[float]] = {}
    for case in cases:
        for observation in case.observations:
            value = observation["value"]
            if value is None:
                continue
            if isinstance(value, bool):
                by_metric.setdefault(observation["metric"], []).append(
                    1.0 if value else 0.0
                )
            elif isinstance(value, (int, float)):
                by_metric.setdefault(observation["metric"], []).append(float(value))
    return {
        metric: (sum(values) / len(values) if values else None)
        for metric, values in sorted(by_metric.items())
    }
