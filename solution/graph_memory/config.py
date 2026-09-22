"""Graph-memory configuration. Every field lands in the run manifest."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class GraphMemoryConfig:
    """All parameters that define one derived-memory version.

    A different model, prompt, chunking, or source corpus produces a
    different derived memory. That version boundary is explicit here so
    derived state is never silently mutated (book §30-31).
    """

    project_root: str = "graph_memory/work/ch4"
    graphrag_version: str = "3.1.2"
    graphrag_executable: str = ".venv/Scripts/graphrag.exe"
    # Models (Ollama-hosted; no cloud dependency for the book runs).
    chat_provider: str = "ollama"
    # ministral-3:8b, not mistral-small: measured ~16s vs ~496s per
    # extraction call on this hardware (12GB VRAM; mistral-small spills
    # to CPU). Extraction quality differences are themselves a finding
    # the chapter reports; override via MEMORY_GRAPH_CHAT_MODEL.
    chat_model: str = "ministral-3:8b"
    embedding_provider: str = "ollama"
    embedding_model: str = "bge-m3"
    ollama_host: str = "http://localhost:11434"
    # GraphRAG indexing choices.
    entity_types: tuple[str, ...] = (
        "organization", "person", "geo", "event", "technology",
    )
    gr_chunk_size: int = 1200
    gr_chunk_overlap: int = 100
    max_gleanings: int = 0  # v3 default is 1; 0 halves extraction calls.
    # The gleaning loop's value is an open question the chapter records;
    # enable explicitly per run if the recall/quality tradeoff is tested.
    claim_extraction: bool = True
    community_level: int = 2
    # Corpus lineage: same canonical sources as the Chapter 3 baseline.
    corpus_version: str = "ch3-fixture-v0.1"
    source_root: str = "fixtures/history"
    # Frozen at index time.
    index_timestamp: str = ""
    code_commit: str = ""
    notes: str = ""
    query_timeout_seconds: int = 180
    index_timeout_seconds: int = 7200

    def to_dict(self) -> dict:
        data = asdict(self)
        data["entity_types"] = list(self.entity_types)
        return data

    @classmethod
    def from_env(cls, **overrides) -> "GraphMemoryConfig":
        base = {
            "project_root": os.environ.get("MEMORY_GRAPH_ROOT", "graph_memory/work/ch4"),
            "query_timeout_seconds": int(os.environ.get("MEMORY_GRAPH_QUERY_TIMEOUT", "180")),
            "ollama_host": os.environ.get(
                "MEMORY_OLLAMA_HOST", "http://localhost:11434"
            ),
            "chat_model": os.environ.get(
                "MEMORY_GRAPH_CHAT_MODEL", "ministral-3:8b"
            ),
            "embedding_model": os.environ.get(
                "MEMORY_GRAPH_EMBED_MODEL", "bge-m3"
            ),
        }
        base.update(overrides)
        return cls(**base)

    def stamped(self, code_commit: str) -> "GraphMemoryConfig":
        """Return a copy with index time and commit frozen in."""
        import dataclasses

        return dataclasses.replace(
            self,
            index_timestamp=datetime.now(timezone.utc).isoformat(),
            code_commit=code_commit,
        )


@dataclass
class IndexCost:
    """Measured indexing cost for one derived-memory build."""

    wall_seconds: float = 0.0
    llm_calls: int = 0  # parsed from GraphRAG logs where available, else -1
    prompt_tokens_estimate: int = -1
    entities: int = 0
    relationships: int = 0
    claims: int = 0
    communities: int = 0
    community_reports: int = 0
    text_units: int = 0
    documents: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QueryCost:
    method: str = ""
    wall_seconds: float = 0.0
    latency_ms: float = 0.0
    context_tokens_estimate: int = 0

    def to_dict(self) -> dict:
        return asdict(self)
