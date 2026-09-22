"""Executors that wire the real Chapter 3, 4, and 5 systems into the registry.

Every capability here produces an **evidence block** and diagnostics; a
single shared reader answers at the end of the episode. Holding the
reader fixed is what makes this a memory-routing experiment rather than a
model-routing one (the chapter stages those separately).

One design decision is worth stating because it differs from Chapter 4's
own conditions. Chapter 4 measured graph memory as *raw retrieval plus a
graph block*, which is the right design for asking whether the graph adds
anything. Routing needs the alternatives to be separable — a capability
that always contains RAG can never lose to RAG — so here each capability
contributes only its own evidence. The two designs answer different
questions and their numbers are not interchangeable.

Availability is honest: a capability whose backing system is missing is
never registered, and one whose health check fails is registered and
marked degraded so that routing can see it and avoid it.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))

from ..state.model import HIGH, LOW, MEDIUM  # noqa: E402
from .registry import (  # noqa: E402
    ASSOCIATIVE,
    GRAPH_BASIC,
    GRAPH_DRIFT,
    GRAPH_GLOBAL,
    GRAPH_LOCAL,
    NONE,
    RAG,
    RAW_EVIDENCE,
    build_registry,
)

# Frozen values behind each budget tier. The router chooses a tier; the
# tier means exactly this and the mapping is recorded in the manifest.
RETRIEVAL_BUDGETS = {LOW: 4, MEDIUM: 8, HIGH: 20}
CONTEXT_CHARS = {LOW: 2000, MEDIUM: 6000, HIGH: 16000}

# Relative cost units, used only for the scalar utility and always
# reported beside the raw dimensions they summarise.
COST_UNITS = {
    NONE: 0.0,
    RAG: 1.0,
    GRAPH_BASIC: 1.5,
    GRAPH_LOCAL: 3.0,
    GRAPH_GLOBAL: 12.0,
    GRAPH_DRIFT: 16.0,
    ASSOCIATIVE: 1.2,
    RAW_EVIDENCE: 2.5,
}


@dataclass
class CapabilityExecution:
    """What one capability contributed, before any reader runs."""

    capability_id: str
    evidence_text: str = ""
    source_ids: list[str] = field(default_factory=list)
    retrieved_ids: list[str] = field(default_factory=list)
    evidence_count: int = 0
    top_score: float = 0.0
    score_margin: float = 0.0
    provenance_available: bool = False
    context_tokens: int = 0
    latency_ms: float = 0.0
    model_calls: int = 0
    graph_expansions: int = 0
    cost_units: float = 0.0
    inner_answer: str = ""
    failed: bool = False
    notes: str = ""

    def observation(self):
        from ..state.model import ActionObservation

        return ActionObservation(
            capability_id=self.capability_id,
            evidence_count=self.evidence_count,
            source_ids=list(self.source_ids),
            answer_text=self.inner_answer,
            abstained=self.evidence_count == 0,
            top_score=self.top_score,
            score_margin=self.score_margin,
            provenance_available=self.provenance_available,
            context_tokens=self.context_tokens,
            latency_ms=self.latency_ms,
            cost_units=self.cost_units,
            model_calls=self.model_calls,
            notes=self.notes,
        )


# -- Chapter 3: retrieval over raw history ------------------------------


def make_rag_executor(baseline):
    """Hybrid retrieval with reranking, bounded by the chosen tier."""
    from memory_baseline.config import ContextConfig, RetrievalConfig
    from memory_baseline.context import assemble

    def execute(state, action) -> CapabilityExecution:
        started = time.perf_counter()
        k = RETRIEVAL_BUDGETS[action.retrieval_budget]
        retrieval_config = RetrievalConfig(
            mode=baseline.config.retrieval.mode,
            candidate_k=max(k * 3, 12),
            lexical_k=max(k * 3, 12),
            dense_k=max(k * 3, 12),
            reranker=baseline.config.retrieval.reranker,
            reranker_model=baseline.config.retrieval.reranker_model,
            rerank_k=k,
        )
        # The retriever is called directly rather than through ``ask``:
        # a capability produces evidence, and the shared reader runs once
        # at the end of the episode. Generating here would double-count
        # reader cost and break the fixed-reader control.
        from memory_baseline.retrieval import Retriever

        retriever = Retriever(baseline.store, baseline.embedder,
                              retrieval_config)
        retrieval = retriever.retrieve(state.query_text)
        ranked = retrieval.reranked or retrieval.fused
        context = assemble(
            ranked[:k],
            ContextConfig(
                max_chars=CONTEXT_CHARS[action.retrieval_budget],
                max_passages=action.context_budget,
            ),
        )
        scores = [chunk.score for chunk in ranked[:k]]
        retrieved: list[str] = []
        for chunk in ranked:
            if chunk.source_id not in retrieved:
                retrieved.append(chunk.source_id)
        return CapabilityExecution(
            capability_id=RAG,
            evidence_text=context.render(),
            source_ids=list(context.sources_covered),
            retrieved_ids=retrieved,
            evidence_count=len(context.admitted),
            top_score=float(scores[0]) if scores else 0.0,
            score_margin=(
                float(scores[0] - scores[1]) if len(scores) > 1 else 0.0
            ),
            provenance_available=True,
            context_tokens=context.admitted_tokens_estimate,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            model_calls=0,
            cost_units=COST_UNITS[RAG],
            notes=f"retrieval_ms={sum(retrieval.latencies_ms.values()):.0f}",
        )

    return execute


def make_raw_evidence_executor(baseline, history_source_ids):
    """Wide, low-selectivity sweep of raw sources: the fallback floor."""
    from memory_baseline.config import ContextConfig
    from memory_baseline.context import assemble

    def execute(state, action) -> CapabilityExecution:
        started = time.perf_counter()
        chunks = baseline.store.chunks_for_sources(list(history_source_ids))
        context = assemble(
            chunks,
            ContextConfig(
                max_chars=CONTEXT_CHARS[HIGH],
                max_passages=max(action.context_budget, 20),
            ),
        )
        return CapabilityExecution(
            capability_id=RAW_EVIDENCE,
            evidence_text=context.render(),
            source_ids=list(context.sources_covered),
            retrieved_ids=list(context.sources_covered),
            evidence_count=len(context.admitted),
            top_score=0.0,
            score_margin=0.0,
            provenance_available=True,
            context_tokens=context.admitted_tokens_estimate,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            cost_units=COST_UNITS[RAW_EVIDENCE],
            notes="unranked sweep of all source artifacts",
        )

    return execute


def make_none_executor():
    """No memory at all. A legitimate action, not a degenerate one."""

    def execute(state, action) -> CapabilityExecution:
        return CapabilityExecution(
            capability_id=NONE,
            evidence_text="",
            evidence_count=0,
            provenance_available=False,
            context_tokens=0,
            latency_ms=0.0,
            cost_units=COST_UNITS[NONE],
            notes="no history retrieved",
        )

    return execute


# -- Chapter 4: persistent derived graph ----------------------------------


def make_graph_executor(graph_system, capability_id: str, mode: str):
    """One GraphRAG query method, with its entity linkage and provenance."""

    def execute(state, action) -> CapabilityExecution:
        started = time.perf_counter()
        from graph_memory.evaluation.adapter import (
            implicated_sources,
            link_entities,
        )

        graph_result = graph_system.backend.query(state.query_text, mode)
        failed = graph_result.answer_text.startswith("[query failed")
        linked = link_entities(state.query_text, graph_system.snapshot)
        implicated = implicated_sources(
            linked, graph_system.snapshot, graph_system.provenance
        )
        block = (
            f"[derived:{mode} search over persistent graph memory; "
            f"linked entities: {', '.join(linked) if linked else 'none'}; "
            f"implicated sources: "
            f"{', '.join(implicated) if implicated else 'none'}]\n"
            f"{graph_result.answer_text}"
        )
        descriptor = {
            GRAPH_BASIC: 1, GRAPH_LOCAL: 1, GRAPH_GLOBAL: 6, GRAPH_DRIFT: 8
        }
        return CapabilityExecution(
            capability_id=capability_id,
            evidence_text="" if failed else block,
            source_ids=list(implicated),
            retrieved_ids=list(implicated),
            evidence_count=0 if failed else max(1, len(implicated)),
            top_score=1.0 if implicated else 0.0,
            score_margin=0.0,
            provenance_available=bool(implicated),
            context_tokens=0 if failed else max(1, len(block) // 4),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            model_calls=descriptor.get(capability_id, 1),
            graph_expansions=len(linked),
            cost_units=COST_UNITS[capability_id],
            inner_answer="" if failed else graph_result.answer_text,
            failed=failed,
            notes=f"linked={len(linked)} implicated={len(implicated)}",
        )

    return execute


# -- Chapter 5: associative activation ---------------------------------------


def make_associative_executor(assoc_memory, store=None):
    """Cue-conditioned propagation over the memory graph.

    The graph is built from the real Chapter 4 snapshot, so this runs over
    the same corpus as every other capability. Evidence text is the source
    artifacts the activated memories point to, fetched from the Chapter 3
    store — the association layer selects, the raw layer supplies text.
    """
    from memory_baseline.config import ContextConfig
    from memory_baseline.context import assemble

    def execute(state, action) -> CapabilityExecution:
        started = time.perf_counter()
        hops = {LOW: 2, MEDIUM: 3, HIGH: 4}[action.retrieval_budget]
        import dataclasses

        config = dataclasses.replace(
            assoc_memory.config,
            propagation=dataclasses.replace(
                assoc_memory.config.propagation, max_hops=hops
            ),
            selection=dataclasses.replace(
                assoc_memory.config.selection,
                max_memories=action.context_budget,
                max_sources=action.context_budget,
            ),
        )
        from associative_memory.pipeline import AssociativeMemory

        runner = AssociativeMemory(
            graph=assoc_memory.graph,
            config=config,
            strategy="conditioned",
        )
        result = runner.retrieve(state.query_text)
        sources = result.admitted_sources()
        activations = [memory.activation for memory in result.admitted]

        evidence_text = ""
        tokens = 0
        if store is not None and sources:
            chunks = store.chunks_for_sources(sources)
            context = assemble(
                chunks,
                ContextConfig(
                    max_chars=CONTEXT_CHARS[action.retrieval_budget],
                    max_passages=action.context_budget,
                ),
            )
            trace_lines = [
                f"[associative path: {' -> '.join(memory.path)} "
                f"(activation {memory.activation:.2f})]"
                for memory in result.admitted[:4]
                if memory.hops >= 1
            ]
            evidence_text = context.render()
            if trace_lines:
                evidence_text = (
                    "\n".join(trace_lines) + "\n\n---\n\n" + evidence_text
                )
            tokens = context.admitted_tokens_estimate + (
                sum(len(line) for line in trace_lines) // 4
            )
            sources = list(context.sources_covered) or sources

        return CapabilityExecution(
            capability_id=ASSOCIATIVE,
            evidence_text=evidence_text,
            source_ids=list(sources),
            retrieved_ids=list(result.explored_sources()),
            evidence_count=len(result.admitted),
            top_score=float(activations[0]) if activations else 0.0,
            score_margin=(
                float(activations[0] - activations[1])
                if len(activations) > 1
                else 0.0
            ),
            provenance_available=bool(sources),
            context_tokens=tokens,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            model_calls=0,
            graph_expansions=len(result.explored),
            cost_units=COST_UNITS[ASSOCIATIVE],
            notes=(
                f"explored={len(result.explored)} "
                f"stopped={result.terminated_because}"
            ),
        )

    return execute


# -- assembling the live registry ---------------------------------------------


@dataclass
class LiveSystems:
    """Handles to the real Chapter 3/4/5 systems, plus what is missing."""

    baseline: object | None = None
    graph_system: object | None = None
    assoc_memory: object | None = None
    history_source_ids: list[str] = field(default_factory=list)
    unavailable: dict[str, str] = field(default_factory=dict)
    degraded: dict[str, str] = field(default_factory=dict)


def build_live_registry(systems: LiveSystems, version="nexus-caps-v0.1"):
    """Register exactly the capabilities whose backing systems are present."""
    executors: dict[str, object] = {NONE: make_none_executor()}
    if systems.baseline is not None:
        executors[RAG] = make_rag_executor(systems.baseline)
        executors[RAW_EVIDENCE] = make_raw_evidence_executor(
            systems.baseline, systems.history_source_ids
        )
    if systems.graph_system is not None:
        for capability_id, mode in (
            (GRAPH_BASIC, "basic"),
            (GRAPH_LOCAL, "local"),
            (GRAPH_GLOBAL, "global"),
            (GRAPH_DRIFT, "drift"),
        ):
            executors[capability_id] = make_graph_executor(
                systems.graph_system, capability_id, mode
            )
    if systems.assoc_memory is not None:
        store = systems.baseline.store if systems.baseline else None
        executors[ASSOCIATIVE] = make_associative_executor(
            systems.assoc_memory, store
        )
    registry = build_registry(executors, version=version)
    for capability_id, reason in systems.degraded.items():
        if capability_id in registry:
            registry.mark_degraded(capability_id, reason)
    for capability_id, reason in systems.unavailable.items():
        if capability_id in registry:
            registry.mark_unavailable(capability_id, reason)
    return registry
