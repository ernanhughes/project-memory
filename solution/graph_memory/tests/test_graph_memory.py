"""Unit tests for graph memory (no LLM calls, no GraphRAG package needed).

Run from the solution directory (system python):
  python -m pytest graph_memory/tests/ -q
"""

from __future__ import annotations

import sys
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))

from memory_baseline import ingest as baseline_ingest  # noqa: E402

from graph_memory.evaluation.consistency import check_pair  # noqa: E402
from graph_memory.evaluation.routing import CONDITIONS, route  # noqa: E402
from graph_memory.evaluation.adapter import link_entities  # noqa: E402
from graph_memory.graphrag_backend.backend import (  # noqa: E402
    GraphEntity,
    GraphSnapshot,
)
from graph_memory.provenance.mapping import build_report  # noqa: E402
from graph_memory.sources.adapters import (  # noqa: E402
    adapt_corpus,
    adapt_source,
    refine_type,
    write_input_docs,
)


def _source(source_id: str, content: str):
    from memory_baseline.ingest import Source, artifact_type, sha1

    return Source(
        source_id=source_id,
        artifact_type=artifact_type(Path(source_id)),
        content=content,
        content_hash=sha1(content),
        timestamp=None,
    )


def test_session_adapter_extracts_stated_participants_only():
    source = _source(
        "session-014.md",
        "# Session 014\n\ndate: 2024-03-04\n"
        "participants: m.okafor, j.lindqvist\n\nHello.",
    )
    (artifact,) = adapt_source(source)
    assert artifact.source_type == "session"
    assert artifact.actor == ("m.okafor", "j.lindqvist")
    assert artifact.timestamp == "2024-03-04"
    assert artifact.thread == "session-014"


def test_unknown_actor_stays_unknown():
    source = _source("notes.md", "# Notes\n\nSome text.")
    (artifact,) = adapt_source(source)
    assert artifact.actor == ()
    assert artifact.timestamp is None


def test_decision_record_adapter():
    source = _source(
        "adr-007.md",
        "# ADR-007\n\ndate: 2024-07-11\nstatus: accepted\n"
        "deciders: m.okafor, j.lindqvist\n\nDecision: x.",
    )
    (artifact,) = adapt_source(source)
    assert artifact.source_type == "decision-record"
    assert artifact.metadata["status"] == "accepted"
    assert artifact.timestamp == "2024-07-11"


def test_commit_log_splits_per_entry():
    source = baseline_ingest.Source(
        source_id="commits.log",
        artifact_type="commit-log",
        content="2024-03-04  init x\n2024-07-22  cut over\n",
        content_hash="abc",
        timestamp=None,
    )
    entries = adapt_source(source)
    assert len(entries) == 2
    assert entries[0].timestamp == "2024-03-04"
    assert entries[0].artifact_id == "commits.log#L1"
    assert all(e.source_type == "commit-log" for e in entries)


def test_refine_type_benchmark_and_experiment():
    assert refine_type("benchmark-note.md", "document", "x") == "benchmark"
    assert (
        refine_type("experiment-contention.md", "document", "x")
        == "experiment"
    )
    assert refine_type("issue-041.md", "issue", "x") == "issue"


def test_write_input_docs_manifest_roundtrip(tmp_path):
    artifacts = adapt_corpus(SOLUTION_ROOT / "fixtures" / "history")
    assert len(artifacts) == 20
    manifest = write_input_docs(artifacts, tmp_path)
    assert len(manifest) == 20
    assert manifest["adr-007.md.txt"] == "adr-007.md"
    assert manifest["commits.log#L1.txt"] == "commits.log#L1"


def test_link_entities_is_deterministic():
    snapshot = GraphSnapshot(
        entities=[
            GraphEntity("e1", "PostgreSQL", "technology"),
            GraphEntity("e2", "SQLite", "technology"),
            GraphEntity("e3", "Importer Service", "system"),
        ]
    )
    question = "What did we decide about PostgreSQL versus SQLite?"
    linked = link_entities(question, snapshot)
    assert linked == link_entities(question, snapshot)
    assert linked == ["PostgreSQL", "SQLite"]
    # No shared tokens: honest empty result, not an error.
    assert link_entities("Where was this discussed?", snapshot) == []


def test_provenance_orphan_detection():
    from graph_memory.graphrag_backend.backend import GraphRelationship

    snapshot = GraphSnapshot(
        entities=[
            GraphEntity("e1", "PostgreSQL", "technology",
                        source_text_units=["u1"]),
            GraphEntity("e2", "Ghost", "technology",
                        source_text_units=["u-missing"]),
        ],
        relationships=[
            GraphRelationship("r1", "PostgreSQL", "SQLite",
                              source_text_units=["u1"]),
        ],
    )

    class FakeBackend:
        def text_unit_sources(self):
            return {"u1": ["adr-007.md.txt"]}

    report = build_report(
        FakeBackend(), snapshot, {"adr-007.md.txt": "adr-007.md"}
    )
    by_name = {c.derived_name: c for c in report.chains}
    assert by_name["PostgreSQL"].artifacts == ["adr-007.md"]
    assert by_name["Ghost"].is_orphan
    assert by_name["Ghost"].broken_links == ["text_unit:u-missing"]
    assert report.orphan_rate("entity") == 0.5


def test_routing_table_covers_all_conditions():
    assert set(CONDITIONS) == {"basic", "local", "global", "drift", "routed"}
    assert route("decision") == "local"
    assert route("global") == "global"
    assert route("locate") == "basic"
    assert route("unknown-family") == "local"


def test_consistency_contradiction_and_agreement():
    pair = check_pair(
        "PostgreSQL was selected.",
        "The database choice remained unresolved.",
        "PostgreSQL", ("SQLite",),
        "q-a", "q-b", "local", "global",
    )
    assert pair.kind == "contradiction"
    pair2 = check_pair(
        "PostgreSQL was selected for new work.",
        "New services should use PostgreSQL.",
        "PostgreSQL", ("SQLite",),
        "q-a", "q-b", "local", "global",
    )
    assert pair2.kind == "agreement"
    pair3 = check_pair(
        "", "PostgreSQL was selected.",
        "PostgreSQL", (),
        "q-a", "q-b", "local", "global",
    )
    assert pair3.kind == "incomparable"
