"""Adapter between the baseline and the Measurement Instrument.

A run flows: Measurement Task → RAG Baseline → retrieval trace →
context trace → answer with evidence → Instrument scorers → metrics,
failure attribution, and costs. Nothing here reimplements scoring;
Chapter 2 owns all of that.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent
INSTRUMENT_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark"
if str(INSTRUMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTRUMENT_ROOT))

from memory_measurement.controls import memory_delta  # noqa: E402
from memory_measurement.manifests import RunManifest  # noqa: E402
from memory_measurement.reports import render_scorecard  # noqa: E402
from memory_measurement.scorers import score_task  # noqa: E402
from memory_measurement.tasks import (  # noqa: E402
    MemoryTask,
    SystemOutput,
)

from .config import BaselineConfig, ContextConfig, RetrievalConfig  # noqa: E402
from .context import assemble  # noqa: E402
from .pipeline import AskResult, Baseline  # noqa: E402

CONDITIONS = (
    "no-memory",
    "lexical",
    "dense",
    "hybrid",
    "hybrid-reranked",
    "best",
    "oracle",
    "full-history",
)


@dataclass
class CaseRecord:
    task_id: str
    condition: str
    answer: str | None
    abstained: bool
    retrieved_source_ids: list[str]
    admitted_source_ids: list[str]
    cited_source_ids: list[str]
    context_tokens_estimate: int
    latencies_ms: dict[str, float]
    observations: list[dict] = field(default_factory=list)


def _retrieval_config(condition: str, base: RetrievalConfig) -> RetrievalConfig | bool:
    if condition == "no-memory":
        return False
    if condition == "lexical":
        return RetrievalConfig(mode="lexical", reranker="none")
    if condition == "dense":
        return RetrievalConfig(mode="dense", reranker="none")
    if condition == "hybrid":
        return RetrievalConfig(mode="hybrid", reranker="none")
    return base  # hybrid-reranked and best use the configured pipeline


def normalize_citation(
    raw: str, history_source_ids: list[str]
) -> tuple[str | None, str]:
    """Map a reader's free-text citation to a history source id.

    Readers cite in ad-hoc forms ("adr-007", "adr-007.md chunk:abc123",
    "source:session-014.md"). Exact identifier match is too strict and
    would punish honest citations, so the mapping normalises case,
    strips "source:" prefixes and "chunk:…" suffixes, and accepts stem
    matches against known history ids. Returns (mapped_id or None,
    evidence_note). Unmapped citations count as fabricated.
    """
    text = raw.strip().lower()
    if text.startswith("source:"):
        text = text[len("source:") :]
    text = text.split("chunk:")[0].split()[0].strip().strip("\"'(),.")
    for known in history_source_ids:
        lowered = known.lower()
        if text == lowered:
            return known, f"mapped:{raw}->{known}"
        stem = lowered.rsplit(".", 1)[0]
        if text == stem or text == stem + ".md":
            return known, f"mapped:{raw}->{known}"
    return None, f"fabricated:{raw}"


def _to_system_output(
    task: MemoryTask,
    result: AskResult,
    chunk_to_source: dict[str, str],
    history_source_ids: list[str] | None = None,
) -> SystemOutput:
    history_source_ids = history_source_ids or []
    if result.retrieval is None:
        # Oracle and full-history conditions provide evidence directly:
        # what was admitted is what was "retrieved".
        retrieved = []
        for chunk in result.context.admitted:
            if chunk.source_id not in retrieved:
                retrieved.append(chunk.source_id)
    else:
        retrieved = []
        for chunk in result.retrieval.fused:
            if chunk.source_id not in retrieved:
                retrieved.append(chunk.source_id)
    admitted = [c.source_id for c in result.context.admitted]
    cited: list[str] = []
    mapping_notes: list[str] = []
    for raw in result.answer.cited_source_ids + result.answer.cited_chunk_ids:
        if raw in chunk_to_source:
            mapped = chunk_to_source[raw]
            note = f"mapped:{raw}->{mapped}"
        else:
            mapped, note = normalize_citation(raw, history_source_ids)
        mapping_notes.append(note)
        if mapped is not None and mapped not in cited:
            cited.append(mapped)
    output = SystemOutput(
        task_id=task.task_id,
        answer=result.answer.text or None,
        cited_sources=tuple(cited),
        retrieved_ids=tuple(retrieved),
        abstained=result.answer.abstained,
        context_tokens=result.context.admitted_tokens_estimate,
    )
    # Stash unmapped citations so the unsupported-source scorer sees them.
    unmapped = [
        note.split("fabricated:", 1)[1]
        for note in mapping_notes
        if note.startswith("fabricated:")
    ]
    if unmapped:
        output = SystemOutput(
            task_id=output.task_id,
            answer=output.answer,
            cited_sources=output.cited_sources + tuple(unmapped),
            retrieved_ids=output.retrieved_ids,
            abstained=output.abstained,
            context_tokens=output.context_tokens,
        )
    return output


def run_condition(
    condition: str,
    tasks: list[MemoryTask],
    baseline: Baseline,
    history_source_ids: list[str],
) -> tuple[list[CaseRecord], dict]:
    """Run every task under one ladder condition."""
    started = time.perf_counter()
    cases: list[CaseRecord] = []
    chunk_to_source: dict[str, str] = {}
    for task in tasks:
        if condition == "oracle":
            chunks = baseline.store.chunks_for_sources(
                list(task.expected_sources)
            )
            for chunk in chunks:
                chunk_to_source[chunk.chunk_id] = chunk.source_id
            context = assemble(chunks, ContextConfig(max_chars=12000,
                                                     max_passages=20))
            answer = baseline.generator.answer(task.prompt, context)
            result = AskResult(task.prompt, None, context, answer)
        elif condition == "full-history":
            # Long-context ceiling diagnostic: as much raw history as a
            # generous budget allows. The budget is recorded, not hidden.
            chunks = baseline.store.chunks_for_sources(history_source_ids)
            for chunk in chunks:
                chunk_to_source[chunk.chunk_id] = chunk.source_id
            context = assemble(
                chunks, ContextConfig(max_chars=60000, max_passages=60)
            )
            answer = baseline.generator.answer(task.prompt, context)
            result = AskResult(task.prompt, None, context, answer)
        else:
            result = baseline.ask(
                task.prompt,
                retrieval_override=_retrieval_config(
                    condition, baseline.config.retrieval
                ),
            )
            if result.retrieval is not None:
                for ranking in (
                    result.retrieval.lexical,
                    result.retrieval.dense,
                    result.retrieval.fused,
                    result.retrieval.reranked,
                ):
                    for chunk in ranking:
                        chunk_to_source.setdefault(
                            chunk.chunk_id, chunk.source_id
                        )
            for chunk in result.context.admitted:
                chunk_to_source.setdefault(chunk.chunk_id, chunk.source_id)
        output = _to_system_output(
            task, result, chunk_to_source, history_source_ids
        )
        observations = score_task(task, output, tuple(history_source_ids))
        latencies = dict(result.retrieval.latencies_ms) if result.retrieval else {}
        latencies["generate"] = result.answer.latency_ms
        cases.append(
            CaseRecord(
                task_id=task.task_id,
                condition=condition,
                answer=output.answer,
                abstained=output.abstained,
                retrieved_source_ids=list(output.retrieved_ids),
                admitted_source_ids=[c.source_id for c in result.context.admitted],
                cited_source_ids=list(output.cited_sources),
                context_tokens_estimate=result.context.admitted_tokens_estimate,
                latencies_ms=latencies,
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
            )
        )
    summary = {
        "condition": condition,
        "tasks": len(tasks),
        "wall_seconds": time.perf_counter() - started,
    }
    return cases, summary


def save_run(
    run_id: str,
    system_name: str,
    condition: str,
    manifest_extra: dict,
    config: BaselineConfig,
    cases: list[CaseRecord],
    runs_root: Path,
) -> Path:
    """Persist a frozen run: manifest, config, per-case records."""
    run_dir = runs_root / run_id / condition
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = RunManifest(
        run_id=run_id,
        system_name=system_name,
        condition=condition,
        corpus_version=manifest_extra.get("corpus_version", "unspecified"),
        task_set_version=manifest_extra.get("task_set_version", "unspecified"),
        model_identity=manifest_extra.get("model_identity", "unspecified"),
        model_version=manifest_extra.get("model_version", "unspecified"),
        prompts=(config.generator.system_prompt,),
        embedding_model=config.embedding.version,
        reranker=config.retrieval.reranker,
        chunking_policy=(
            f"{config.chunking.policy}:{config.chunking.target_chars}:"
            f"{config.chunking.overlap_chars}"
        ),
        retrieval_budget=f"candidates={config.retrieval.candidate_k}",
        context_budget=(
            f"chars={config.context.max_chars},"
            f"passages={config.context.max_passages}"
        ),
        memory_configuration=condition,
        code_commit=manifest_extra.get("code_commit", "unspecified"),
        notes=manifest_extra.get("notes", ""),
    )
    (run_dir / "manifest.json").write_text(
        manifest.to_json(), encoding="utf-8"
    )
    (run_dir / "config.json").write_text(
        json.dumps(config.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with (run_dir / "cases.jsonl").open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(
                json.dumps(
                    {
                        "task_id": case.task_id,
                        "condition": case.condition,
                        "answer": case.answer,
                        "abstained": case.abstained,
                        "retrieved_source_ids": case.retrieved_source_ids,
                        "admitted_source_ids": case.admitted_source_ids,
                        "cited_source_ids": case.cited_source_ids,
                        "context_tokens_estimate": case.context_tokens_estimate,
                        "latencies_ms": case.latencies_ms,
                        "observations": case.observations,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    return run_dir


def metric_means(cases: list[CaseRecord]) -> dict[str, float | None]:
    by_metric: dict[str, list[float]] = {}
    for case in cases:
        for observation in case.observations:
            value = observation["value"]
            if isinstance(value, bool):
                by_metric.setdefault(observation["metric"], []).append(
                    1.0 if value else 0.0
                )
            elif isinstance(value, (int, float)):
                by_metric.setdefault(observation["metric"], []).append(
                    float(value)
                )
    return {
        metric: (sum(values) / len(values) if values else None)
        for metric, values in sorted(by_metric.items())
    }


def scorecard_text(
    cases: list[CaseRecord],
    manifest: RunManifest,
    from_saved_run: Path | None = None,
) -> str:
    from memory_measurement.observations import MemoryObservation

    observations = [
        MemoryObservation(
            task_id=case.task_id,
            metric=o["metric"],
            value=o["value"],
            evidence=tuple(o["evidence"]),
            failure_class=o["failure_class"],
            grader=o["grader"],
        )
        for case in cases
        for o in case.observations
    ]
    return render_scorecard(observations, manifest)


def run_stamped_id(prefix: str = "ch3") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}"
