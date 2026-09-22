"""Matched final-reader comparison. Extra GraphRAG inference is reported separately."""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))
INSTRUMENT_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark"
if str(INSTRUMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTRUMENT_ROOT))

from memory_baseline.config import ContextConfig  # noqa: E402
from memory_baseline.context import ContextTrace, assemble  # noqa: E402
from memory_baseline.evaluation import (  # noqa: E402
    _to_system_output,
    normalize_citation,
)
from memory_baseline.pipeline import AskResult, Baseline  # noqa: E402
from memory_measurement.scorers import score_task  # noqa: E402
from memory_measurement.tasks import MemoryTask, SystemOutput  # noqa: E402

from graph_memory.graphrag_backend.backend import (  # noqa: E402
    GraphQueryResult,
    GraphSnapshot,
)
from graph_memory.graphrag_backend.microsoft import (  # noqa: E402
    MicrosoftGraphRAGBackend,
)
from graph_memory.provenance.mapping import (  # noqa: E402
    ProvenanceReport,
    build_report,
)

_WORD_RE = re.compile(r"[a-z0-9]{4,}")
_STOPWORDS = frozenset(
    "what which when where whom whose that this these those with from into "
    "about does were have been will would should could there their them they "
    "your have does event store used using used project history during team "
    "data system service layer cache query tasks task major themes occurred "
    "period quarter related connected influence influenced evidence decided "
    "decision rationale adopted rejected".split()
)


def link_entities(question: str, snapshot: GraphSnapshot) -> list[str]:
    """Link question tokens to graph entity names (deterministic).

    Substring token overlap between the question and entity names/titles.
    This is deliberately crude: it is the *floor* of entity linking, and
    any stronger linker later must beat it. Returns entity names.
    """
    tokens = {t for t in _WORD_RE.findall(question.lower())} - _STOPWORDS
    linked: list[str] = []
    for entity in snapshot.entities:
        name_tokens = set(_WORD_RE.findall(entity.name.lower()))
        if tokens & name_tokens:
            linked.append(entity.name)
    return linked


def implicated_sources(
    entity_names: list[str],
    snapshot: GraphSnapshot,
    report: ProvenanceReport,
) -> list[str]:
    """Canonical artifacts behind the linked entities, in stable order."""
    by_name = {}
    for chain in report.chains:
        if chain.derived_kind != "entity":
            continue
        by_name.setdefault(chain.derived_name, []).extend(chain.artifacts)
    seen: list[str] = []
    for name in entity_names:
        for artifact in by_name.get(name, []):
            if artifact not in seen:
                seen.append(artifact)
    return seen


@dataclass
class GraphAskResult:
    task_id: str
    mode: str
    answer_text: str
    abstained: bool
    cited_source_ids: list[str]
    retrieved_source_ids: list[str]
    admitted_source_ids: list[str]
    context_tokens_estimate: int
    latencies_ms: dict[str, float]
    graph_result: GraphQueryResult
    linked_entities: list[str] = field(default_factory=list)
    implicated_sources: list[str] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)
    final_context: str = ""


class GraphMemorySystem:
    """Strong RAG plus one GraphRAG query method, one reader."""

    def __init__(
        self,
        baseline: Baseline,
        backend: MicrosoftGraphRAGBackend,
        history_source_ids: list[str],
        raw_context: ContextConfig | None = None,
    ) -> None:
        self.baseline = baseline
        self.backend = backend
        self.history_source_ids = history_source_ids
        self.raw_context = raw_context or baseline.config.context
        self._snapshot: GraphSnapshot | None = None
        self._provenance: ProvenanceReport | None = None
        self._manifest: dict | None = None

    def prepare(self) -> None:
        """Load snapshot + provenance once per run (read-only over output)."""
        self._snapshot = self.backend.snapshot()
        input_manifest = {
            f: a
            for f, a in self._input_manifest().items()
        }
        self._provenance = build_report(
            self.backend, self._snapshot, input_manifest
        )

    def _input_manifest(self) -> dict:
        # Re-derive the input manifest deterministically from adapters.
        from graph_memory.sources.adapters import (
            adapt_corpus,
            write_input_docs,
        )
        import tempfile

        artifacts = adapt_corpus(self.backend.corpus_root())
        with tempfile.TemporaryDirectory() as tmp:
            manifest = write_input_docs(artifacts, Path(tmp))
        return manifest

    @property
    def snapshot(self) -> GraphSnapshot:
        if self._snapshot is None:
            self.prepare()
        assert self._snapshot is not None
        return self._snapshot

    @property
    def provenance(self) -> ProvenanceReport:
        if self._provenance is None:
            self.prepare()
        assert self._provenance is not None
        return self._provenance

    def ask(self, task: MemoryTask, mode: str) -> GraphAskResult:
        """Matched final evidence budget; graph work is additional and recorded."""
        started = time.perf_counter()
        graph = (self.backend.query(task.prompt, mode) if mode != "best"
                 else GraphQueryResult(task.prompt, "best", ""))
        retrieval = self.baseline.retriever.retrieve(task.prompt)
        budget = self.raw_context.max_chars
        block = ""
        if graph.answer_text:
            header = f"[derived:{mode}; fallible synthesis, not a canonical source]\n"
            block = (header + graph.answer_text)[:budget // 3]
        separator = "\n\n---\n\n" if block else ""
        context = strict_assemble(retrieval.reranked, self.raw_context,
                                  budget - len(block) - len(separator))
        evidence = context.render() + separator + block
        answer = self.baseline.generator.answer(task.prompt, _Evidence(evidence))
        if "call failed:" in answer.model:
            raise RuntimeError(answer.model)
        chunk_to_source = {c.chunk_id: c.source_id for c in retrieval.reranked}
        cited = []
        for value in answer.cited_source_ids + answer.cited_chunk_ids:
            mapped = chunk_to_source.get(value)
            if mapped is None:
                mapped, _ = normalize_citation(value, self.history_source_ids)
            if mapped is not None and mapped not in cited:
                cited.append(mapped)
        # Score only direct raw evidence admitted to the final reader. Graph
        # lineage is a separate diagnostic, not proof that a source was read.
        admitted = list(context.sources_covered)
        output = SystemOutput(task_id=task.task_id, answer=answer.text,
            cited_sources=tuple(cited), retrieved_ids=tuple(admitted),
            abstained=answer.abstained, context_tokens=len(evidence) // 4,
            notes=f"graph:{mode}; source metrics use admitted raw evidence")
        observations = score_task(task, output, tuple(self.history_source_ids))
        result = GraphAskResult(
            task_id=task.task_id, mode=mode, answer_text=answer.text,
            abstained=answer.abstained, cited_source_ids=cited,
            retrieved_source_ids=list(dict.fromkeys(c.source_id for c in retrieval.reranked)),
            admitted_source_ids=admitted, context_tokens_estimate=len(evidence) // 4,
            latencies_ms={"graph": graph.latency_ms,
                "raw_retrieval": sum(retrieval.latencies_ms.values()),
                "generate": answer.latency_ms,
                "total": round((time.perf_counter()-started)*1000, 1)},
            graph_result=graph, implicated_sources=list(graph.source_artifacts),
            observations=[{"metric": o.metric, "value": o.value,
                "failure_class": o.failure_class, "evidence": list(o.evidence),
                "grader": o.grader} for o in observations])
        result.final_context = evidence
        return result


def strict_assemble(ranked, cfg, budget):
    """Admit whole passages including headers and separators within budget."""
    context = ContextTrace()
    seen = set()
    for chunk in ranked:
        fingerprint = " ".join(chunk.text.lower().split())
        if fingerprint in seen:
            context.dropped_duplicates += 1
            continue
        proposed = ContextTrace(admitted=context.admitted + [chunk])
        if len(proposed.render()) > budget or len(context.admitted) >= cfg.max_passages:
            context.dropped_over_budget += 1
            continue
        seen.add(fingerprint)
        context.admitted.append(chunk)
    context.admitted_chars = len(context.render())
    context.admitted_tokens_estimate = context.admitted_chars // 4
    context.sources_covered = list(dict.fromkeys(c.source_id for c in context.admitted))
    return context


class _Evidence:
    """Minimal ContextTrace-shaped wrapper carrying combined evidence text."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.admitted = []
        self.admitted_tokens_estimate = max(1, len(text) // 4)

    def render(self) -> str:
        return self._text
