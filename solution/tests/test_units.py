"""Unit tests: pure logic, no services required."""

from pathlib import Path

from memory_baseline import ingest
from memory_baseline.config import BaselineConfig, ChunkingConfig
from memory_baseline.context import ContextConfig, assemble
from memory_baseline.embeddings import HashingEmbedder, cosine
from memory_baseline.evaluation import _to_system_output
from memory_baseline.generation import _parse_response
from memory_baseline.health import HealthIssue, HealthReport
from memory_baseline.retrieval import OverlapReranker, reciprocal_rank_fusion
from memory_baseline.routing import (
    MemoryRoute,
    classify_route,
    evaluate_router,
    guidance_for,
    parse_explicit_route,
    route_for_request,
)
from memory_baseline.storage import ScoredChunk


def make_chunk(cid, source, text, score=1.0, rank=1):
    return ScoredChunk(
        chunk_id=cid, source_id=source, text=text,
        section=None, score=score, rank=rank,
    )


# -- ingestion --------------------------------------------------------


def test_discover_and_parse(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# Title\n\nSome words.", encoding="utf-8")
    (tmp_path / "empty.md").write_text("   ", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "x.md").write_text("hidden", encoding="utf-8")
    found = ingest.discover(tmp_path)
    assert [p.name for p in found] == ["a.md", "empty.md"]
    source = ingest.parse(tmp_path / "a.md", tmp_path)
    assert source is not None and source.source_id == "a.md"
    assert ingest.parse(tmp_path / "empty.md", tmp_path) is None


def test_discover_skips_build_artifacts(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const x = 1;\n",
                                               encoding="utf-8")
    for skipped in ("dist", "build", "coverage", "target", ".next",
                    ".turbo", "node_modules", "__pycache__", ".venv", "venv"):
        artifact = tmp_path / skipped
        artifact.mkdir(exist_ok=True)
        (artifact / "bundle.js").write_text("var x = 1;\n", encoding="utf-8")
    (tmp_path / "dist" / "notes.md").write_text("stale build doc\n",
                                                encoding="utf-8")
    found = ingest.discover(tmp_path)
    assert [p.relative_to(tmp_path).as_posix() for p in found] == [
        "src/index.ts"
    ]


def test_chunk_ids_deterministic() -> None:
    source = ingest.Source("s.md", "document", "Hello world. " * 200, "h", None)
    cfg = ChunkingConfig(policy="sentence", target_chars=200, overlap_chars=40)
    first = [c.chunk_id for c in ingest.chunk_source(source, cfg)]
    second = [c.chunk_id for c in ingest.chunk_source(source, cfg)]
    assert first == second and len(first) > 1


def test_no_empty_chunks_and_provenance() -> None:
    source = ingest.Source("s.md", "document", "# A\n\nText here.\n\n# B\n\nMore.",
                           "h", "2024-01-01")
    chunks = ingest.chunk_source(source, ChunkingConfig(policy="section"))
    assert chunks and all(c.text.strip() for c in chunks)
    assert all(c.source_id == "s.md" for c in chunks)
    assert chunks[0].char_start == 0
    assert chunks[-1].char_end == len(source.content)


def test_section_split_marks_headings() -> None:
    spans = ingest.chunk_section("# A\ntext\n## B\nmore")
    assert len(spans) == 2
    assert spans[0][2] == "# A"
    assert spans[1][2] == "## B"


# -- retrieval --------------------------------------------------------


def test_rrf_prefers_consensus() -> None:
    a = make_chunk("a", "s1", "alpha")
    b = make_chunk("b", "s2", "beta")
    c = make_chunk("c", "s3", "gamma")
    fused = reciprocal_rank_fusion([[a, b, c], [b, c]])
    assert [x.chunk_id for x in fused[:2]] == ["b", "c"]


def test_overlap_reranker_reorders() -> None:
    chunks = [
        make_chunk("x", "s1", "unrelated weather report"),
        make_chunk("y", "s2", "PostgreSQL event store decision"),
    ]
    ranked = OverlapReranker().rerank("event store decision", chunks, k=2)
    assert ranked[0].chunk_id == "y"


def test_hashing_embedder_deterministic() -> None:
    embedder = HashingEmbedder(32)
    first = embedder.embed(["hello world"])
    second = embedder.embed(["hello world"])
    assert first.vectors == second.vectors
    assert abs(cosine(first.vectors[0], second.vectors[0]) - 1.0) < 1e-9


# -- context ----------------------------------------------------------


def test_assemble_dedupes_and_budgets() -> None:
    chunks = [
        make_chunk("a", "s1", "same text here"),
        make_chunk("b", "s2", "same text here"),
        make_chunk("c", "s3", "different " * 500),
    ]
    trace = assemble(chunks, ContextConfig(max_chars=100, max_passages=5))
    assert [c.chunk_id for c in trace.admitted] == ["a"]
    assert trace.dropped_duplicates == 1
    assert trace.dropped_over_budget == 1
    assert trace.admitted_tokens_estimate >= 1


def test_assemble_respects_passage_cap() -> None:
    chunks = [make_chunk(str(i), f"s{i}", f"text number {i}") for i in range(9)]
    trace = assemble(chunks, ContextConfig(max_chars=10**6, max_passages=3))
    assert len(trace.admitted) == 3
    assert trace.dropped_over_budget == 6


# -- generation -------------------------------------------------------


def test_parse_json_response() -> None:
    text, cited, abstained = _parse_response(
        'prefix {"answer": "PostgreSQL", "cited_ids": ["source:adr-007.md"], '
        '"abstain": false} suffix'
    )
    assert text == "PostgreSQL"
    assert cited == ["source:adr-007.md"]
    assert abstained is False


def test_parse_plain_text_fallback() -> None:
    text, cited, abstained = _parse_response("Just some words.")
    assert text == "Just some words."
    assert cited == [] and abstained is False


# -- evaluation adapter -------------------------------------------------


def test_system_output_mapping() -> None:
    from memory_measurement.tasks import MemoryTask, SystemOutput

    from memory_baseline.pipeline import AskResult
    from memory_baseline.context import ContextTrace
    from memory_baseline.generation import Answer

    task = MemoryTask(
        task_id="t", family="decision", prompt="q", history_ref="h",
        expected_sources=("s1",),
    )
    retrieval = None
    context = ContextTrace(
        admitted=[make_chunk("c1", "s1", "words")],
        admitted_chars=5, admitted_tokens_estimate=2,
        sources_covered=["s1"],
    )
    answer = Answer(text="yes", cited_source_ids=["source:s1"],
                    cited_chunk_ids=["c1"])
    output = _to_system_output(
        task, AskResult("q", retrieval, context, answer), {"c1": "s1"}, ["s1"]
    )
    assert isinstance(output, SystemOutput)
    # No retrieval trace but admitted context: admission counts as retrieval.
    assert output.retrieved_ids == ("s1",)
    assert set(output.cited_sources) == {"s1"}
    assert output.context_tokens == 2


# -- health -------------------------------------------------------------


def test_health_report_render() -> None:
    report = HealthReport(
        healthy=False, sources=3, chunks=10,
        issues=[HealthIssue("missing-hnsw", "no vector index")],
    )
    text = report.render()
    assert "UNHEALTHY" in text
    assert "missing-hnsw" in text


def test_citation_normalization() -> None:
    from memory_baseline.evaluation import normalize_citation

    history = ["adr-007.md", "session-014.md"]
    assert normalize_citation("adr-007.md chunk:abc123", history)[0] == "adr-007.md"
    assert normalize_citation("ADR-007", history)[0] == "adr-007.md"
    assert normalize_citation("source:session-014.md", history)[0] == "session-014.md"
    assert normalize_citation("benchmark-126", history)[0] is None


def test_oracle_counts_admitted_as_retrieved() -> None:
    from memory_baseline.context import ContextTrace
    from memory_baseline.evaluation import _to_system_output
    from memory_baseline.generation import Answer
    from memory_baseline.pipeline import AskResult
    from memory_measurement.tasks import MemoryTask

    task = MemoryTask(
        task_id="t", family="decision", prompt="q", history_ref="h",
        expected_sources=("s1",),
    )
    context = ContextTrace(
        admitted=[make_chunk("c1", "s1", "words")],
        admitted_chars=5, admitted_tokens_estimate=2,
        sources_covered=["s1"],
    )
    result = AskResult("q", None, context, Answer(text="yes", model="m"))
    output = _to_system_output(task, result, {"c1": "s1"}, ["s1"])
    assert output.retrieved_ids == ("s1",)


def test_default_config_freezes() -> None:
    config = BaselineConfig()
    assert config.retrieval.mode == "hybrid"
    assert config.embedding.model == "bge-m3"
    assert "distinguish" in config.generator.system_prompt.lower() or \
        "proposed" in config.generator.system_prompt


# -- routing ------------------------------------------------------------


def test_routing_contract_passes() -> None:
    report = evaluate_router()
    assert report["passed"], report["failures"]
    assert (report["recall_correct"], report["influence_correct"],
            report["ambiguous_correct"]) == (7, 7, 5)
    # 19 contract fixtures + 2 explicit-override checks = 21 checks.
    assert report["examples"] == 19
    assert (report["checks_passed"], report["checks_total"]) == (21, 21)


def test_recall_interrogative_beats_action_verb() -> None:
    # "Why did we originally choose X" asks about the past choice.
    decision = classify_route("Why did we originally choose PostgreSQL?")
    assert decision.route is MemoryRoute.RECALL
    assert decision.source == "deterministic"
    assert not decision.ambiguous


def test_explicit_route_overrides_inference() -> None:
    assert classify_route("Where did we discuss pgvector?",
                          explicit="influence").route is MemoryRoute.INFLUENCE
    assert classify_route("Fix the migration.",
                          explicit="recall").route is MemoryRoute.RECALL
    explicit = classify_route("anything", explicit="recall")
    assert explicit.source == "explicit" and not explicit.ambiguous


def test_malformed_route_fails_closed() -> None:
    import pytest

    with pytest.raises(ValueError):
        parse_explicit_route("historical-ish")
    with pytest.raises(ValueError):
        route_for_request("query", route="sometime")


def test_ambiguous_queries_stay_observable() -> None:
    for query in ("PostgreSQL schema", "The old design", "Current state"):
        decision = classify_route(query)
        assert decision.route is MemoryRoute.INFLUENCE
        assert decision.ambiguous
        assert "ambiguous" in decision.reason or "fallback" in decision.reason


def test_route_guidance_labels_contract() -> None:
    assert "historical reconstruction" in guidance_for(MemoryRoute.RECALL)
    assert "not yet implemented" in guidance_for(MemoryRoute.INFLUENCE)


# -- temporal interpretation --------------------------------------------


def test_temporal_contract_passes() -> None:
    from memory_baseline.temporal import evaluate_temporal

    report = evaluate_temporal()
    assert report["passed"], report["categories"]
    assert (report["checks_passed"], report["checks_total"]) == (16, 16)
    assert set(report["categories"]) == {
        "current", "valid_time", "known_at", "bitemporal",
        "planned_effective", "supersession", "correction", "ordering",
        "incomplete_history", "unmodelled",
    }


def test_temporal_standpoint_rejects_bad_params() -> None:
    import pytest

    from memory_baseline.temporal import TemporalStandpoint

    assert TemporalStandpoint(mode="current").mode == "current"
    with pytest.raises(ValueError, match="TEMPORAL_BAD_STANDPOINT"):
        TemporalStandpoint(mode="valid_at")
    with pytest.raises(ValueError, match="TEMPORAL_BAD_STANDPOINT"):
        TemporalStandpoint(mode="valid_at", valid_at="last summer")
    with pytest.raises(ValueError, match="TEMPORAL_BAD_TIMESTAMP"):
        TemporalStandpoint(mode="current", valid_at="last summer")
    with pytest.raises(ValueError, match="TEMPORAL_BAD_STANDPOINT"):
        TemporalStandpoint(mode="bitemporal",
                           valid_at="2026-07-20T00:00:00Z")
