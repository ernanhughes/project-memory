"""The adapter boundary: book concepts on one side, packages on the other.

Microsoft GraphRAG is the first experimental implementation behind this
boundary, not the definition of memory. A different package, a
purpose-built memory graph, or a future replacement must be able to
implement this protocol without changing any caller.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol

QUERY_MODES = ("basic", "local", "global", "drift")


@dataclass
class GraphEntity:
    entity_id: str
    name: str
    kind: str
    description: str = ""
    source_text_units: list[str] = field(default_factory=list)
    degree: int = 0


@dataclass
class GraphRelationship:
    relationship_id: str
    source: str
    target: str
    description: str = ""
    weight: float = 0.0
    source_text_units: list[str] = field(default_factory=list)


@dataclass
class GraphClaim:
    claim_id: str
    subject: str
    description: str = ""
    claim_type: str = ""
    status: str = ""
    source_text_units: list[str] = field(default_factory=list)


@dataclass
class GraphCommunity:
    community_id: str
    title: str = ""
    summary: str = ""
    level: int = 0
    size: int = 0
    source_text_units: list[str] = field(default_factory=list)


@dataclass
class GraphSnapshot:
    """Inspectable derived state: what the indexer thinks it understood."""

    entities: list[GraphEntity] = field(default_factory=list)
    relationships: list[GraphRelationship] = field(default_factory=list)
    claims: list[GraphClaim] = field(default_factory=list)
    communities: list[GraphCommunity] = field(default_factory=list)
    text_units: int = 0
    documents: int = 0

    def to_dict(self) -> dict:
        return {
            "entities": [asdict(e) for e in self.entities],
            "relationships": [asdict(r) for r in self.relationships],
            "claims": [asdict(c) for c in self.claims],
            "communities": [asdict(c) for c in self.communities],
            "text_units": self.text_units,
            "documents": self.documents,
        }


@dataclass
class GraphQueryResult:
    question: str
    method: str
    answer_text: str
    wall_seconds: float = 0.0
    latency_ms: float = 0.0
    context_tokens_estimate: int = 0
    entities_seen: list[str] = field(default_factory=list)
    relationships_seen: list[str] = field(default_factory=list)
    text_units_used: list[str] = field(default_factory=list)
    communities_used: list[str] = field(default_factory=list)
    raw_output: str = ""
    context_data: dict = field(default_factory=dict)
    source_artifacts: list[str] = field(default_factory=list)
    # The public query API does not expose complete model-call/token accounting.
    llm_calls: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IndexReport:
    output_dir: str = ""
    corpus_version: str = ""
    corpus_hash: str = ""
    graphrag_version: str = ""
    chat_model: str = ""
    embedding_model: str = ""
    wall_seconds: float = 0.0
    llm_responses: int = -1
    total_tokens: int = -1
    entities: int = 0
    relationships: int = 0
    claims: int = 0
    communities: int = 0
    community_reports: int = 0
    text_units: int = 0
    documents: int = 0
    failures: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class StructuredMemoryBackend(Protocol):
    """Persistent derived memory over a fixed source corpus."""

    def index(self, force: bool = False) -> IndexReport:
        """Build (or rebuild) derived state from the configured corpus."""
        ...

    def query_basic(self, question: str) -> GraphQueryResult:
        """Vector-over-text-units search: the GraphRAG-internal RAG analogue."""
        ...

    def query_local(self, question: str) -> GraphQueryResult:
        """Entity-centred search over graph neighbourhoods and text."""
        ...

    def query_global(self, question: str) -> GraphQueryResult:
        """Map/reduce synthesis over community reports."""
        ...

    def query_drift(self, question: str) -> GraphQueryResult:
        """Primer-plus-follow-up traversal from community context."""
        ...

    def query(self, question: str, mode: str) -> GraphQueryResult:
        """Dispatch to one of basic/local/global/drift."""
        ...

    def snapshot(self) -> GraphSnapshot:
        """Load the current derived state for inspection."""
        ...

    def manifest(self) -> dict:
        """Version record: package, models, prompts, corpus, config."""
        ...
