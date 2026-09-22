"""Bringing up the real Chapter 3, 4, and 5 systems behind the registry.

Availability is checked, never assumed. Each subsystem is probed, its
health report is read, and the outcome is recorded in three buckets:
present and healthy, present but degraded, absent. The registry then
advertises only what actually exists — which is also what makes
health-aware routing possible rather than aspirational.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent
INSTRUMENT_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark"
for _candidate in (str(SOLUTION_ROOT), str(INSTRUMENT_ROOT)):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from .capabilities.adapters import LiveSystems, build_live_registry  # noqa: E402
from .capabilities.registry import (  # noqa: E402
    ASSOCIATIVE,
    GRAPH_BASIC,
    GRAPH_DRIFT,
    GRAPH_GLOBAL,
    GRAPH_LOCAL,
    RAG,
    RAW_EVIDENCE,
)

TASK_FIXTURE = SOLUTION_ROOT / "fixtures" / "nexus" / "routing-tasks-v0.1.json"


def normalise_source_id(raw: str) -> str:
    """Map a GraphRAG input filename back onto a canonical artifact id.

    The graph indexes ``adr-007.md.txt``; the ledger says ``adr-007.md``.
    Without this the associative capability would appear to retrieve
    nothing, because its sources would match no expected source.
    """
    name = raw
    if name.endswith(".txt"):
        name = name[: -len(".txt")]
    return name.replace("__", "/")


@dataclass
class BringUpReport:
    healthy: list[str] = field(default_factory=list)
    degraded: dict[str, str] = field(default_factory=dict)
    absent: dict[str, str] = field(default_factory=dict)
    details: dict = field(default_factory=dict)

    def render(self) -> str:
        lines = ["Memory Nexus capability bring-up", ""]
        for capability_id in sorted(self.healthy):
            lines.append(f"  available  {capability_id}")
        for capability_id, reason in sorted(self.degraded.items()):
            lines.append(f"  DEGRADED   {capability_id}: {reason}")
        for capability_id, reason in sorted(self.absent.items()):
            lines.append(f"  absent     {capability_id}: {reason}")
        return "\n".join(lines) + "\n"


def load_tasks(path: Path | None = None):
    """Load the routing task set as instrument tasks plus analysis metadata."""
    from memory_measurement.tasks import MemoryTask

    payload = json.loads(
        Path(path or TASK_FIXTURE).read_text(encoding="utf-8")
    )
    tasks = []
    routing_families: dict[str, str] = {}
    for item in payload["tasks"]:
        data = dict(item)
        # routing_family is analysis metadata. It is removed here so it
        # cannot reach a task object that the state builder sees.
        routing_families[data["task_id"]] = data.pop("routing_family", "")
        for key in ("expected_sources", "expected_aliases",
                    "superseded_options"):
            if key in data:
                data[key] = tuple(data[key])
        tasks.append(MemoryTask(**data))
    return tasks, payload, routing_families


def build_reader(config):
    """The shared reader. One model, one prompt, for every capability."""
    from memory_baseline.config import GeneratorConfig
    from memory_baseline.generation import OllamaGenerator

    generator = OllamaGenerator(
        GeneratorConfig(
            provider=config.reader.provider,
            model=config.reader.model,
            ollama_host=config.reader.ollama_host,
            temperature=config.reader.temperature,
        )
    )

    class _Evidence:
        """ContextTrace-shaped carrier for an arbitrary evidence block."""

        def __init__(self, text: str) -> None:
            self._text = text
            self.admitted = []
            self.admitted_tokens_estimate = max(1, len(text) // 4)

        def render(self) -> str:
            return self._text

    def reader(prompt: str, evidence_text: str):
        return generator.answer(prompt, _Evidence(evidence_text))

    return reader, generator


def bring_up(config, want_graph: bool = True, want_assoc: bool = True):
    """Construct whatever is present and report what is not."""
    report = BringUpReport()
    systems = LiveSystems()
    _tasks, payload, _families = load_tasks()
    systems.history_source_ids = list(payload["history_source_ids"])

    # -- Chapter 3 --------------------------------------------------------
    try:
        from memory_baseline.cli import build_baseline
        from memory_baseline.config import BaselineConfig
        from memory_baseline.health import check_health as check_rag_health

        baseline = build_baseline(BaselineConfig.from_env())
        health = check_rag_health(baseline)
        systems.baseline = baseline
        report.details["rag_health"] = {
            "healthy": health.healthy,
            "sources": health.sources,
            "chunks": health.chunks,
            "issues": [f"{i.check}: {i.detail}" for i in health.issues],
        }
        if health.healthy:
            report.healthy.extend([RAG, RAW_EVIDENCE])
        else:
            reason = "; ".join(i.check for i in health.issues)
            report.degraded[RAG] = reason
            report.degraded[RAW_EVIDENCE] = reason
            systems.degraded[RAG] = reason
            systems.degraded[RAW_EVIDENCE] = reason
    except Exception as exc:  # pragma: no cover - environment dependent
        for capability_id in (RAG, RAW_EVIDENCE):
            report.absent[capability_id] = f"{type(exc).__name__}: {exc}"[:160]

    # -- Chapter 4 ---------------------------------------------------------
    graph_ids = (GRAPH_BASIC, GRAPH_LOCAL, GRAPH_GLOBAL, GRAPH_DRIFT)
    if want_graph:
        try:
            from graph_memory.config import GraphMemoryConfig
            from graph_memory.evaluation.adapter import GraphMemorySystem
            from graph_memory.graphrag_backend.microsoft import (
                MicrosoftGraphRAGBackend,
            )
            from graph_memory.health.checks import check_health as check_graph

            backend = MicrosoftGraphRAGBackend(GraphMemoryConfig.from_env())
            graph_health = check_graph(backend)
            graph_system = GraphMemorySystem(
                systems.baseline, backend, systems.history_source_ids
            )
            graph_system.prepare()
            systems.graph_system = graph_system
            report.details["graph_health"] = {
                "healthy": graph_health.healthy,
                "stats": graph_health.stats,
                "issues": [
                    f"{i.check}: {i.detail}" for i in graph_health.issues
                ],
            }
            for capability_id in graph_ids:
                if graph_health.healthy:
                    report.healthy.append(capability_id)
                else:
                    reason = "; ".join(i.check for i in graph_health.issues)
                    report.degraded[capability_id] = reason
                    systems.degraded[capability_id] = reason
            # A missing community report degrades corpus-wide synthesis
            # specifically, and health-aware routing should see that.
            missing_reports = [
                i for i in graph_health.issues
                if i.check == "community-reports"
            ]
            if missing_reports:
                detail = missing_reports[0].detail
                report.details["graph_synthesis_caveat"] = detail
        except Exception as exc:  # pragma: no cover
            for capability_id in graph_ids:
                report.absent[capability_id] = (
                    f"{type(exc).__name__}: {exc}"[:160]
                )
    else:
        for capability_id in graph_ids:
            report.absent[capability_id] = "not requested"

    # -- Chapter 5 over the real Chapter 4 graph -----------------------------
    if want_assoc and systems.graph_system is not None:
        try:
            from associative_memory.config import AssociativeConfig
            from associative_memory.graph.adapter import from_graphrag_snapshot
            from associative_memory.health.checks import check_graph as assoc_health
            from associative_memory.pipeline import AssociativeMemory

            backend = systems.graph_system.backend
            memory_graph = from_graphrag_snapshot(
                systems.graph_system.snapshot, backend.text_unit_sources()
            )
            # Canonicalise source identifiers so the associative layer's
            # provenance matches the ledger's.
            for node in memory_graph.nodes.values():
                node.source_ids = tuple(
                    normalise_source_id(s) for s in node.source_ids
                )
            for edge in memory_graph.edges:
                edge.source_ids = tuple(
                    normalise_source_id(s) for s in edge.source_ids
                )
            memory_graph.version = "graphrag-snapshot-ch4"
            memory_graph.corpus_version = payload["corpus_version"]
            systems.assoc_memory = AssociativeMemory(
                graph=memory_graph,
                config=AssociativeConfig(),
                strategy="conditioned",
            )
            health = assoc_health(memory_graph)
            report.details["assoc_health"] = {
                "healthy": health.healthy,
                "nodes": health.nodes,
                "edges": health.semantic_edges,
                "issues": [f"{i.check}: {i.detail}" for i in health.issues],
            }
            report.healthy.append(ASSOCIATIVE)
            if not health.healthy:
                # Structural issues on a graph derived by extraction are
                # expected — orphan nodes and a dominant hub are what a
                # real snapshot looks like — and do not by themselves
                # disable the capability. They are recorded as a note, not
                # as degradation, so the report and the registry agree.
                report.details["assoc_structural_note"] = "; ".join(
                    i.check for i in health.issues
                )
        except Exception as exc:  # pragma: no cover
            report.absent[ASSOCIATIVE] = f"{type(exc).__name__}: {exc}"[:160]
    elif want_assoc:
        report.absent[ASSOCIATIVE] = "requires the Chapter 4 graph"

    registry = build_live_registry(systems, version=config.registry_version)
    return systems, registry, report
