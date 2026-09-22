"""Deterministic controlled fixtures for the E7 suite.

Ground-truth ledger: claims, support groups, derivation relations,
source spans, echo relations and injected failures. All scorers run
against this truth; no LLM judge is involved.

IDs reuse the book's frozen running examples (adr-007, session-014,
session-033, session-019, incident-021, runbook-006, session-040,
session-044) plus Chapter 7 fixture IDs. No ID is invented outside
this ledger. The losing-side SQLite preference lives in `session-033`
(canonical ledger); an earlier revision of this fixture mislabelled it
`session-017`, which was never a canonical ID — repaired 2026-09-19.
The `s33-false` span is an explicitly injected fabrication attributed
to the same session for the error-localisation suite, flagged as such
in its text; it is not canonical session-033 content.
"""

from __future__ import annotations

# ------------------------------------------------------------------
# Source spans: (node_id, artifact_id, text, kind)
# ------------------------------------------------------------------

SPANS: list[tuple[str, str, str]] = [
    ("s14-contention", "session-014",
     "Load test 12 June: concurrent writes to the SQLite event store "
     "serialise on the write lock; p95 append latency 840ms under "
     "32 writers."),
    ("s19-benchmark", "session-019",
     "Benchmark 19 June: PostgreSQL sustains 40x the concurrent-write "
     "throughput of SQLite on the importer workload; SQLite serialises "
     "writers."),
    ("s44-replicate", "session-044",
     "Benchmark rerun 2 July on an independent harness: PostgreSQL "
     "holds 35x concurrent-write throughput over SQLite; the contention "
     "finding replicates."),
    ("i21-incident", "incident-021",
     "Importer failure 24 June: SQLite write-lock timeout under "
     "concurrent load; 3 retries exhausted; events delayed 40 minutes."),
    ("a07-rationale", "adr-007",
     "Decision: move the event store to PostgreSQL. Rationale: "
     "sustained concurrent-write contention (load test, benchmark) "
     "caused importer failures. Tradeoff accepted: higher operational "
     "cost."),
    ("a07-decision", "adr-007",
     "Decision: the event store uses PostgreSQL."),
    ("r06-echo", "runbook-006",
     "Runbook (August): the event store runs on PostgreSQL."),
    ("s17-sqlite-case", "session-033",
     "Pre-decision note: keep SQLite for operational simplicity; "
     "single-file backup, no server to run. (Losing side of the "
     "decision; canonical session-033 preference.)"),
    ("s40-other-importer", "session-040",
     "Benchmark 28 June of the analytics importer: SQLite adequate; "
     "no contention observed. (A different importer.)"),
    ("s33-false", "session-033",
     "Session note: SQLite lost 14% of writes during the June load "
     "window. (Ledger truth: fabricated; no other artifact records "
     "any write loss.)"),
    ("w10-summary", "wiki-010",
     "Wiki: we use PostgreSQL for performance."),
    ("inv183-span", "invoice-183",
     "Invoice 183: routine infrastructure renewal, within budget; "
     "unrelated to the Project Alpha budget variance."),
]

# ------------------------------------------------------------------
# Claims: (claim_id, text)
# ------------------------------------------------------------------

CLAIMS: list[tuple[str, str]] = [
    ("claim-main",
     "PostgreSQL was selected because concurrent-write contention "
     "was harming the importer."),
    ("claim-atomic",
     "PostgreSQL was selected."),
    ("claim-contention",
     "SQLite experienced concurrent-write contention."),
    ("claim-14pct",
     "SQLite lost 14% of writes."),
    ("claim-perf",
     "PostgreSQL was chosen for general performance."),
    ("claim-causal-gap",
     "The benchmark proved PostgreSQL resolves concurrency failures."),
    ("claim-budget",
     "Project Alpha overspent because of invoice 183."),
    ("claim-redis",
     "The importer failures were caused by the Redis cache."),
    ("claim-narrow",
     "The 19 June benchmark measured 40x concurrent-write throughput."),
]

# ------------------------------------------------------------------
# Support groups: claim_id -> list of frozensets (OR of ANDs).
# Only these (claim, evidence) pairs license belief.
# ------------------------------------------------------------------

SUPPORT_GROUPS: dict[str, list[frozenset[str]]] = {
    "claim-main": [
        frozenset({"s19-benchmark", "i21-incident", "a07-rationale"}),
        frozenset({"s44-replicate", "i21-incident", "a07-rationale"}),
    ],
    "claim-atomic": [frozenset({"a07-rationale"})],
    "claim-contention": [frozenset({"s14-contention"})],
    "claim-14pct": [],
    "claim-perf": [],
    "claim-causal-gap": [],
    "claim-budget": [],
    "claim-redis": [],
    "claim-narrow": [frozenset({"s19-benchmark"})],
}

# Flat entailment truth derived from the groups.
ENTAILS: set[tuple[str, str]] = {
    (claim, member)
    for claim, groups in SUPPORT_GROUPS.items()
    for group in groups
    for member in group
}

# Topical-but-non-supporting pairs (retrievable, relevant-looking,
# licensing nothing). The provenance-precision trap set.
TOPICAL_ONLY: set[tuple[str, str]] = {
    ("claim-main", "s17-sqlite-case"),
    ("claim-main", "s40-other-importer"),
    ("claim-main", "w10-summary"),
    ("claim-main", "r06-echo"),
    ("claim-contention", "s40-other-importer"),
    ("claim-budget", "inv183-span"),
    ("claim-14pct", "s33-false"),  # traceable, fabricated: grounds, not true
    ("claim-perf", "w10-summary"),
}

# ------------------------------------------------------------------
# Derivation / echo structure over derived nodes.
# ------------------------------------------------------------------

DERIVED_NODES: list[tuple[str, str]] = [
    ("ext-rel-1", "extracted relation: PostgreSQL REPLACED SQLite"),
    ("comm-17", "community summary: SQLite contention forced the "
                "PostgreSQL move; SQLite lost 14% of writes. "
                "(14% figure invented here)"),
    ("ctx-9", "retrieved context for the why-question"),
    ("ans-5", "reader output repeating the 14% figure"),
    ("rel-redis-1", "harmful derived relation: Redis CAUSED "
                    "importer failures (no raw grounding)"),
]

# (child, parent)
DERIVED_FROM: list[tuple[str, str]] = [
    ("ext-rel-1", "a07-rationale"),
    ("ext-rel-1", "s19-benchmark"),
    ("comm-17", "ext-rel-1"),
    ("comm-17", "s14-contention"),
    ("ctx-9", "comm-17"),
    ("ctx-9", "i21-incident"),
    ("ans-5", "ctx-9"),
]

# (echo, echoed)
ECHO_OF: list[tuple[str, str]] = [
    ("r06-echo", "a07-decision"),
    ("w10-summary", "a07-decision"),
]

# ------------------------------------------------------------------
# Per-stage support truth for VeriTrail-style verification.
# claim_id -> {stage: supported-by-inputs or None}
# ------------------------------------------------------------------

STAGE_SUPPORT: dict[str, dict[str, bool | None]] = {
    "claim-main": {"source": True, "extraction": True, "graph_node": True,
                   "summary": True, "context": True, "reader": True},
    "claim-14pct": {"source": True, "extraction": True, "graph_node": True,
                    "summary": False, "context": False, "reader": False},
    "claim-redis": {"source": True, "extraction": True, "graph_node": False,
                    "summary": False, "context": False, "reader": False},
}

# Injected error stages (ground truth for E7-G).
ERROR_STAGE_TRUTH: dict[str, str | None] = {
    "claim-main": None,
    "claim-14pct": "summary",
    "claim-redis": "graph_node",
}

# ------------------------------------------------------------------
# Claim-extraction fixtures (E7-B): sentence -> expected atomic claims.
# ------------------------------------------------------------------

EXTRACTION_CASES: list[dict] = [
    {"sentence": "PostgreSQL was selected.",
     "expected": ["PostgreSQL was selected."]},
    {"sentence": "PostgreSQL was selected because SQLite contention "
                 "caused the importer failures.",
     "expected": ["PostgreSQL was selected.",
                  "SQLite experienced contention.",
                  "The contention contributed to importer failures.",
                  "The contention/importer failure contributed to "
                  "the decision."]},
    {"sentence": "We chose PostgreSQL after reviewing the benchmark, "
                 "though operational cost was higher.",
     "expected": ["We chose PostgreSQL after reviewing the benchmark.",
                  "Operational cost was higher."]},
    {"sentence": "The importer never failed under SQLite.",
     "expected": ["The importer never failed under SQLite."],
     "negated": True},
    {"sentence": "If contention returns, we will revisit the decision.",
     "expected": ["If contention returns, we will revisit the decision."],
     "conditional": True},
    {"sentence": "The operator reported that the importer timed out.",
     "expected": ["The operator reported that the importer timed out."],
     "attributed": True},
    {"sentence": "They fixed it next quarter.",
     "expected": [],
     "ambiguous": True},
]

# ------------------------------------------------------------------
# Echo ladder (E7-D): graded restatements of the adr-007 decision.
# All five are echoes (truth); a token-overlap detector is measured
# at each rung to map where it stops working.
# ------------------------------------------------------------------

ECHO_LADDER: list[dict] = [
    {"id": "e0-exact",
     "text": "Decision: the event store uses PostgreSQL."},
    {"id": "e1-near",
     "text": "Decision: the event store uses PostgreSQL (migrated "
             "in July)."},
    {"id": "e2-heavy",
     "text": "Following the July migration, our events live in "
             "Postgres now."},
    {"id": "e3-summary",
     "text": "We use PostgreSQL for the event store."},
    {"id": "e4-terminology",
     "text": "The event-sourcing substrate was rehomed to PG after "
             "the write-contention episode."},
]

# ------------------------------------------------------------------
# Reader outputs for answer/evidence divergence (E7-J).
# ------------------------------------------------------------------

DIVERGENCE_CASES: list[dict] = [
    {"id": "j1", "answer_correct": True, "evidence_correct": True},
    {"id": "j2", "answer_correct": True, "evidence_correct": False,
     "note": "right answer, cites the losing-side session-033 passage"},
    {"id": "j3", "answer_correct": False, "evidence_correct": True,
     "note": "wrong conclusion, but the contention citation is genuine"},
    {"id": "j4", "answer_correct": False, "evidence_correct": False},
]

# ------------------------------------------------------------------
# Chapter 5/6 trace annotations (kept, never scored as support).
# ------------------------------------------------------------------

RETRIEVAL_TRACES: dict[str, list[str]] = {
    "claim-budget": ["query", "Bill", "ProjectAlpha", "budget",
                     "invoice-183"],
    "claim-main": ["query", "importer", "incident-021", "session-019",
                   "adr-007"],
}

CONTROL_TRACES: dict[str, list[str]] = {
    "claim-redis": ["RAG insufficient", "Graph Local", "answer"],
    "claim-main": ["RAG", "insufficient", "Graph Local", "answer"],
}


def build_graph():
    """Assemble the fixture lineage graph."""
    from .lineage import Edge, EdgeKind, LineageGraph, Node, NodeKind

    graph = LineageGraph()
    for claim_id, text in CLAIMS:
        graph.add_node(Node(claim_id, NodeKind.CLAIM, text))
    for span_id, artifact, text in SPANS:
        graph.add_node(Node(span_id, NodeKind.SOURCE_SPAN,
                            f"{artifact}: {text[:60]}"))
    for node_id, label in DERIVED_NODES:
        graph.add_node(Node(node_id, NodeKind.DERIVED, label))
    for claim_id, groups in SUPPORT_GROUPS.items():
        for group in groups:
            for member in group:
                graph.add_edge(Edge(claim_id, member,
                                    EdgeKind.SUPPORTED_BY))
    for child, parent in DERIVED_FROM:
        graph.add_edge(Edge(child, parent, EdgeKind.DERIVED_FROM))
    for echo, echoed in ECHO_OF:
        graph.add_edge(Edge(echo, echoed, EdgeKind.ECHO_OF))
    # Claim-level derivation for the hallucination trace.
    graph.add_edge(Edge("claim-14pct", "ans-5", EdgeKind.DERIVED_FROM))
    graph.add_edge(Edge("claim-redis", "rel-redis-1",
                        EdgeKind.DERIVED_FROM))
    graph.retrieval_traces.update(RETRIEVAL_TRACES)
    graph.control_traces.update(CONTROL_TRACES)
    return graph


def build_supports():
    """ClaimSupport structures mirroring SUPPORT_GROUPS."""
    from .evidence import ClaimSupport, SupportEdge, SupportGroup

    supports: dict[str, ClaimSupport] = {}
    for claim_id, groups in SUPPORT_GROUPS.items():
        support = ClaimSupport(claim_id)
        for i, group in enumerate(sorted(groups, key=sorted)):
            gid = f"{claim_id}-g{i}"
            support.groups.append(SupportGroup(gid, claim_id,
                                               tuple(sorted(group))))
            for member in sorted(group):
                support.edges.append(SupportEdge(
                    claim_id, member, gid,
                    licensed_by=(member,)))
        supports[claim_id] = support
    return supports


def token_overlap(a: str, b: str) -> float:
    """Jaccard overlap over lowercased word tokens."""
    import re

    def toks(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    ta, tb = toks(a), toks(b)
    if not ta and not tb:
        return 1.0
    return len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0


def echo_detector(text: str, source_text: str, threshold: float) -> bool:
    """Deterministic echo heuristic: high token overlap with source."""
    return token_overlap(text, source_text) >= threshold
