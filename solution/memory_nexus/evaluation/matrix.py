"""The task-by-capability matrix: does specialisation actually exist?

This is the chapter's central artifact and it comes before any router.
Every task is run through every capability under matched conditions, and
the result answers a question that decides whether the rest of the
chapter has a subject:

    Does any capability win tasks that another loses?

If one capability dominates every row, there is no routing problem and
the honest conclusion is that the Nexus is premature. The matrix is what
makes that falsifiable rather than rhetorical.

Cells are cached on disk by (task, capability, corpus, reader, code
commit). A GraphRAG DRIFT query takes twenty-six minutes on the book's
hardware; without resumable caching the matrix could not be built at all,
and the cache key includes everything that would invalidate a cell.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
INSTRUMENT_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark"
for candidate in (str(SOLUTION_ROOT), str(INSTRUMENT_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from memory_measurement.scorers import score_task  # noqa: E402
from memory_measurement.tasks import SystemOutput  # noqa: E402


@dataclass
class MatrixCell:
    """One (task, capability) measurement."""

    query_id: str
    capability_id: str
    measured: bool = False
    answer: str | None = None
    abstained: bool = False
    retrieved_ids: list[str] = field(default_factory=list)
    admitted_ids: list[str] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    failure_classes: list[str] = field(default_factory=list)
    context_tokens: int = 0
    latency_ms: float = 0.0
    capability_latency_ms: float = 0.0
    reader_latency_ms: float = 0.0
    model_calls: int = 0
    graph_expansions: int = 0
    cost_units: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "MatrixCell":
        return cls(**payload)


class CapabilityMatrix:
    """Cells plus the accessors the oracle and the analysis need."""

    def __init__(self, manifest: dict | None = None) -> None:
        self.cells: dict[tuple[str, str], MatrixCell] = {}
        self.manifest = manifest or {}

    def put(self, cell: MatrixCell) -> None:
        self.cells[(cell.query_id, cell.capability_id)] = cell

    def get(self, query_id: str, capability_id: str) -> MatrixCell | None:
        return self.cells.get((query_id, capability_id))

    def by_query(self) -> dict[str, list[MatrixCell]]:
        grouped: dict[str, list[MatrixCell]] = {}
        for (query_id, _cap), cell in sorted(self.cells.items()):
            grouped.setdefault(query_id, []).append(cell)
        return grouped

    def by_capability(self) -> dict[str, list[MatrixCell]]:
        grouped: dict[str, list[MatrixCell]] = {}
        for (_q, capability_id), cell in sorted(self.cells.items()):
            grouped.setdefault(capability_id, []).append(cell)
        return grouped

    def query_ids(self) -> list[str]:
        return sorted({query_id for query_id, _ in self.cells})

    def capability_ids(self) -> list[str]:
        return sorted({cap for _, cap in self.cells})

    # -- the specialisation question ---------------------------------------

    def dominance(self, utility) -> dict:
        """Does any one capability win every task it was measured on?

        Returns the per-capability win count, the set of tasks each
        capability uniquely wins, and whether a single capability
        dominates. A dominating capability means no routing problem.
        """
        wins: dict[str, list[str]] = {}
        unique_wins: dict[str, list[str]] = {}
        contested = 0
        for query_id, cells in self.by_query().items():
            measured = [cell for cell in cells if cell.measured]
            if not measured:
                continue
            scored = sorted(
                ((utility.score(cell), cell.capability_id) for cell in measured),
                key=lambda item: (-item[0], item[1]),
            )
            best_score = scored[0][0]
            winners = [cap for score, cap in scored if score >= best_score - 1e-9]
            for capability_id in winners:
                wins.setdefault(capability_id, []).append(query_id)
            if len(winners) == 1:
                unique_wins.setdefault(winners[0], []).append(query_id)
            if len({round(score, 6) for score, _ in scored}) > 1:
                contested += 1
        total = len(
            [q for q, cells in self.by_query().items()
             if any(c.measured for c in cells)]
        )
        dominator = None
        for capability_id, won in wins.items():
            if len(won) == total and total > 0:
                dominator = capability_id
        return {
            "tasks_measured": total,
            "tasks_with_a_score_difference": contested,
            "wins": {k: sorted(v) for k, v in sorted(wins.items())},
            "win_counts": {k: len(v) for k, v in sorted(wins.items())},
            "unique_wins": {
                k: sorted(v) for k, v in sorted(unique_wins.items())
            },
            "single_capability_dominates": dominator,
        }

    def fixed_policy_scores(self, utility) -> dict[str, dict]:
        """Mean dimensions for each always-this-capability policy."""
        report: dict[str, dict] = {}
        for capability_id, cells in self.by_capability().items():
            measured = [cell for cell in cells if cell.measured]
            if not measured:
                continue
            report[capability_id] = {
                "tasks": len(measured),
                "quality": round(
                    sum(utility.quality(c) for c in measured) / len(measured), 4
                ),
                "evidence": round(
                    sum(utility.evidence(c) for c in measured) / len(measured), 4
                ),
                "harm": round(
                    sum(utility.harm(c) for c in measured) / len(measured), 4
                ),
                "utility": round(
                    sum(utility.score(c) for c in measured) / len(measured), 4
                ),
                "cost_units": round(
                    sum(c.cost_units for c in measured) / len(measured), 3
                ),
                "latency_ms": round(
                    sum(c.latency_ms for c in measured) / len(measured), 1
                ),
                "context_tokens": round(
                    sum(c.context_tokens for c in measured) / len(measured), 1
                ),
            }
        return report

    # -- persistence ---------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "manifest": self.manifest,
            "cells": [cell.to_dict() for cell in self.cells.values()],
        }

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: Path) -> "CapabilityMatrix":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        matrix = cls(manifest=payload.get("manifest", {}))
        for item in payload.get("cells", []):
            matrix.put(MatrixCell.from_dict(item))
        return matrix


def cache_key(task_id: str, capability_id: str, context: dict) -> str:
    """Stable identity for one cell under one set of frozen variables."""
    payload = json.dumps(
        {"task": task_id, "capability": capability_id, **context},
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def run_cell(
    task,
    capability,
    reader,
    history_source_ids: list[str],
    state_builder,
    action,
) -> MatrixCell:
    """Execute one capability on one task and score the result.

    The reader is the same object for every capability, and it is given
    only the evidence that capability produced. Nothing here reimplements
    a scorer: ``score_task`` is Chapter 2's, unmodified.
    """
    started = time.perf_counter()
    state = state_builder(task)
    execution = capability.execute(state, action)
    reader_started = time.perf_counter()
    answer = reader(task.prompt, execution.evidence_text)
    reader_ms = (time.perf_counter() - reader_started) * 1000.0

    cited = _map_citations(answer, history_source_ids)
    output = SystemOutput(
        task_id=task.task_id,
        answer=answer.text or None,
        cited_sources=tuple(cited),
        retrieved_ids=tuple(execution.source_ids),
        abstained=answer.abstained,
        context_tokens=execution.context_tokens,
        notes=f"capability:{capability.capability_id}",
    )
    observations = score_task(task, output, tuple(history_source_ids))
    metrics = {
        o.metric: (1.0 if o.value is True else 0.0 if o.value is False else o.value)
        for o in observations
    }
    return MatrixCell(
        query_id=task.task_id,
        capability_id=capability.capability_id,
        measured=True,
        answer=output.answer,
        abstained=output.abstained,
        retrieved_ids=list(execution.retrieved_ids),
        admitted_ids=list(execution.source_ids),
        cited_ids=list(cited),
        metrics=metrics,
        failure_classes=[
            o.failure_class for o in observations if o.failure_class
        ],
        context_tokens=execution.context_tokens,
        latency_ms=(time.perf_counter() - started) * 1000.0,
        capability_latency_ms=execution.latency_ms,
        reader_latency_ms=reader_ms,
        model_calls=execution.model_calls + 1,
        graph_expansions=execution.graph_expansions,
        cost_units=execution.cost_units,
        notes=execution.notes,
    )


def _map_citations(answer, history_source_ids: list[str]) -> list[str]:
    """Reuse the Chapter 3 citation normaliser; no second convention."""
    from memory_baseline.evaluation import normalize_citation

    cited: list[str] = []
    for raw in list(answer.cited_source_ids) + list(answer.cited_chunk_ids):
        mapped, _note = normalize_citation(raw, history_source_ids)
        if mapped is not None and mapped not in cited:
            cited.append(mapped)
        elif mapped is None and raw not in cited:
            # Unmapped citations are fabrication and must reach the
            # unsupported-source scorer rather than being dropped.
            cited.append(raw)
    return cited
