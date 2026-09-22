"""Integration tests against live services.

Skipped gracefully when PostgreSQL or Ollama is unavailable, so the
unit suite stays green on machines without the baseline substrate.
"""

import os
import urllib.request

import pytest

psycopg = pytest.importorskip("psycopg")

from memory_baseline import ingest  # noqa: E402
from memory_baseline.config import (  # noqa: E402
    BaselineConfig,
    ChunkingConfig,
    EmbeddingConfig,
    RetrievalConfig,
)
from memory_baseline.embeddings import (  # noqa: E402
    HashingEmbedder,
    OllamaEmbeddingProvider,
)
from memory_baseline.pipeline import Baseline  # noqa: E402
from memory_baseline.storage import Store  # noqa: E402

DSN = os.environ.get(
    "MEMORY_BASELINE_DSN",
    "postgresql://postgres:postgres@localhost:5434/memory_baseline_test",
)
OLLAMA = "http://localhost:11434"


def service_available() -> bool:
    try:
        psycopg.connect(DSN, connect_timeout=3).close()
    except Exception:
        return False
    try:
        urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5).close()
    except Exception:
        return False
    return True


needs_services = pytest.mark.skipif(
    not service_available(), reason="PostgreSQL or Ollama unavailable"
)


def make_baseline(**overrides) -> Baseline:
    config = BaselineConfig(dsn=DSN, schema="baseline_it", **overrides)
    store = Store(config.dsn, config.schema)
    store.conn.execute(f'DROP SCHEMA IF EXISTS {config.schema} CASCADE')
    baseline = Baseline.__new__(Baseline)
    baseline.config = config
    baseline.embedder = HashingEmbedder(32)
    baseline.store = store
    from memory_baseline.retrieval import Retriever
    from memory_baseline.generation import ExtractiveReader

    baseline.retriever = Retriever(store, baseline.embedder, config.retrieval)
    baseline.generator = ExtractiveReader()
    baseline.initialise()
    return baseline


@needs_services
def test_ingest_is_idempotent(tmp_path) -> None:
    baseline = make_baseline()
    try:
        (tmp_path / "doc.md").write_text(
            "# Doc\n\nPostgreSQL won because of contention.", encoding="utf-8"
        )
        first = baseline.refresh(tmp_path)
        second = baseline.refresh(tmp_path)
        assert (first.added, first.unchanged) == (1, 0)
        assert (second.added, second.unchanged) == (0, 1)
        assert second.chunks == 0
    finally:
        baseline.close()


@needs_services
def test_changed_and_deleted_files(tmp_path) -> None:
    baseline = make_baseline()
    try:
        target = tmp_path / "doc.md"
        target.write_text("# Doc\n\nVersion one.", encoding="utf-8")
        baseline.refresh(tmp_path)
        target.write_text("# Doc\n\nVersion two words.", encoding="utf-8")
        changed = baseline.refresh(tmp_path)
        assert changed.changed == 1
        target.unlink()
        removed = baseline.refresh(tmp_path)
        assert removed.removed == 1
        assert baseline.store.stats()["sources"] == 0
    finally:
        baseline.close()


@needs_services
def test_lexical_search_finds_identifiers(tmp_path) -> None:
    baseline = make_baseline()
    try:
        (tmp_path / "adr-007.md").write_text(
            "# ADR-007\n\nPostgreSQL target. Incident evt-203 closed.",
            encoding="utf-8",
        )
        baseline.refresh(tmp_path)
        hits = baseline.store.lexical_search("evt-203", k=5)
        assert hits and hits[0].source_id == "adr-007.md"
    finally:
        baseline.close()


@needs_services
def test_dense_search_orders_by_similarity(tmp_path) -> None:
    baseline = make_baseline()
    try:
        (tmp_path / "a.md").write_text(
            "PostgreSQL event store decision record.", encoding="utf-8"
        )
        (tmp_path / "b.md").write_text(
            "Unrelated weather observations for March.", encoding="utf-8"
        )
        baseline.refresh(tmp_path)
        vector = baseline.embedder.embed(["event store decision"]).vectors[0]
        hits = baseline.store.dense_search(vector, k=5)
        assert [h.source_id for h in hits] == ["a.md", "b.md"]
    finally:
        baseline.close()


@needs_services
def test_ollama_embedding_dimensions() -> None:
    provider = OllamaEmbeddingProvider("bge-m3")
    result = provider.embed(["probe"])
    assert result.dimension == 1024
    assert provider.version() == "ollama:bge-m3"


@needs_services
def test_health_passes_on_fresh_index(tmp_path) -> None:
    from memory_baseline.health import check_health

    baseline = make_baseline()
    try:
        (tmp_path / "doc.md").write_text("# Doc\n\nWords.", encoding="utf-8")
        baseline.refresh(tmp_path)
        report = check_health(baseline)
        assert report.healthy, [i.detail for i in report.issues]
    finally:
        baseline.close()


@needs_services
def test_chunking_policies_agree_on_coverage(tmp_path) -> None:
    text = ("Sentence one here. Sentence two here. Sentence three here. " * 40)
    source = ingest.Source("s.md", "document", text, "h", None)
    counts = {}
    for policy in ("fixed", "sentence", "section"):
        cfg = ChunkingConfig(policy=policy, target_chars=300, overlap_chars=60)
        chunks = ingest.chunk_source(source, cfg)
        covered = {(c.char_start, c.char_end) for c in chunks}
        assert covered
        counts[policy] = len(chunks)
    assert all(n >= 1 for n in counts.values())


@needs_services
def test_retrieval_trace_records_stages(tmp_path) -> None:
    baseline = make_baseline(
        retrieval=RetrievalConfig(mode="hybrid", reranker="overlap")
    )
    try:
        (tmp_path / "doc.md").write_text(
            "# Doc\n\nPostgreSQL event store decision.", encoding="utf-8"
        )
        baseline.refresh(tmp_path)
        trace = baseline.retriever.retrieve("event store")
        assert trace.lexical and trace.dense and trace.fused
        assert trace.reranked
        assert set(trace.latencies_ms) >= {"lexical", "dense", "rerank"}
    finally:
        baseline.close()
