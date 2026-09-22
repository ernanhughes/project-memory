"""Structural health checks over a built derived index (book §40).

These checks prove structural health, never semantic correctness: counts,
mapping coverage, duplicates, and build freshness. A healthy report means
the index is inspectable; whether it is *right* is what the experiments
measure.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))

from graph_memory.graphrag_backend.microsoft import (  # noqa: E402
    MicrosoftGraphRAGBackend,
)
from graph_memory.provenance.mapping import build_report  # noqa: E402


@dataclass
class HealthIssue:
    check: str
    detail: str


@dataclass
class GraphHealth:
    healthy: bool
    issues: list[HealthIssue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def report_text(self, manifest: dict | None = None) -> str:
        lines = ["Graph Memory Health", ""]
        info = manifest or {}
        lines.append(
            f"Source corpus version: {info.get('corpus_version', '?')} "
            f"(hash {info.get('corpus_hash', '?')})"
        )
        lines.append(f"GraphRAG version: {info.get('graphrag_version', '?')}")
        lines.append(f"Chat model: {info.get('chat_model', '?')}")
        lines.append(
            f"Embedding model: {info.get('embedding_model', '?')}"
        )
        lines.append("")
        for key in (
            "documents", "text_units", "entities", "relationships",
            "claims", "communities", "community_reports",
        ):
            lines.append(f"{key.replace('_', ' ').title()}: "
                         f"{self.stats.get(key, '?')}")
        lines.append("")
        lines.append(
            f"Entities without source mappings: "
            f"{self.stats.get('entities_without_sources', '?')}")
        lines.append(
            f"Relationships without source mappings: "
            f"{self.stats.get('relationships_without_sources', '?')}")
        lines.append(
            f"Claims without evidence mapping: "
            f"{self.stats.get('claims_without_sources', '?')}")
        lines.append(
            f"Duplicate/near-duplicate entities: "
            f"{self.stats.get('duplicate_entities', '?')}")
        lines.append(
            f"Indexing failures: "
            f"{self.stats.get('index_failures', '?')}")
        lines.append(
            f"Last complete build: {info.get('index_timestamp', '?')}")
        lines.append("")
        lines.append(f"Verdict: {'HEALTHY' if self.healthy else 'UNHEALTHY'}")
        for issue in self.issues:
            lines.append(f"  - [{issue.check}] {issue.detail}")
        return "\n".join(lines)


def _normalise_name(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())


def _duplicates(names: list[str]) -> list[str]:
    """Exact collisions after normalisation plus close fuzzy matches.

    Catches both "A. NOVAK"/"A.NOVAK" (spacing/punctuation splits) and
    near-misses like "J. LINDQVIST"/"J. LINQVIST" (extraction typos).
    """
    import difflib

    dupes: list[str] = []
    by_key: dict[str, str] = {}
    for name in names:
        key = _normalise_name(name)
        if key in by_key and by_key[key] != name and name not in dupes:
            dupes.append(f"{by_key[key]} ~ {name}")
        by_key.setdefault(key, name)
    surface = sorted(set(names))
    for i in range(len(surface)):
        for j in range(i + 1, len(surface)):
            pair = f"{surface[i]} ~ {surface[j]}"
            if pair in dupes or f"{surface[j]} ~ {surface[i]}" in dupes:
                continue
            if _normalise_name(surface[i]) == _normalise_name(surface[j]):
                continue  # already covered above
            ratio = difflib.SequenceMatcher(
                None, surface[i].lower(), surface[j].lower()
            ).ratio()
            if ratio >= 0.85:
                dupes.append(pair)
    return dupes


def check_health(
    backend: MicrosoftGraphRAGBackend, index_failures: int = 0
) -> GraphHealth:
    issues: list[HealthIssue] = []
    stats: dict = {"index_failures": index_failures}
    try:
        snapshot = backend.snapshot()
    except Exception as exc:
        return GraphHealth(
            healthy=False,
            issues=[HealthIssue("snapshot", f"cannot load index: {exc}")],
            stats=stats,
        )
    stats.update(
        {
            "documents": snapshot.documents,
            "text_units": snapshot.text_units,
            "entities": len(snapshot.entities),
            "relationships": len(snapshot.relationships),
            "claims": len(snapshot.claims),
            "communities": len(snapshot.communities),
            "community_reports": sum(
                1 for c in snapshot.communities if c.summary
            ),
        }
    )
    if snapshot.documents == 0:
        issues.append(HealthIssue("documents", "no documents indexed"))
    if not snapshot.entities:
        issues.append(HealthIssue("entities", "no entities extracted"))
    if not snapshot.relationships:
        issues.append(HealthIssue("relationships", "no relationships"))
    manifest = {
        f: a
        for f, a in _input_manifest(backend).items()
    }
    report = build_report(backend, snapshot, manifest)
    stats["entities_without_sources"] = sum(
        1 for c in report.chains
        if c.derived_kind == "entity" and c.is_orphan
    )
    stats["relationships_without_sources"] = sum(
        1 for c in report.chains
        if c.derived_kind == "relationship" and c.is_orphan
    )
    stats["claims_without_sources"] = sum(
        1 for c in report.chains
        if c.derived_kind == "claim" and c.is_orphan
    )
    stats["overall_orphan_rate"] = report.orphan_rate()
    dupes = _duplicates([e.name for e in snapshot.entities])
    stats["duplicate_entities"] = dupes
    missing_reports = [
        c.community_id
        for c in snapshot.communities
        if not c.summary
    ]
    stats["communities_without_reports"] = missing_reports
    if missing_reports:
        issues.append(
            HealthIssue(
                "community-reports",
                f"communities without reports: {missing_reports} "
                f"(extraction/generation failure — see index logs)",
            )
        )
    if stats["entities_without_sources"]:
        issues.append(
            HealthIssue(
                "entity-provenance",
                f"{stats['entities_without_sources']} entities trace to "
                f"no canonical artifact",
            )
        )
    if stats["relationships_without_sources"]:
        issues.append(
            HealthIssue(
                "relationship-provenance",
                f"{stats['relationships_without_sources']} relationships "
                f"trace to no canonical artifact",
            )
        )
    if stats["claims_without_sources"] or any(c.broken_links for c in report.chains):
        issues.append(HealthIssue("provenance", "incomplete source chains exist"))
    if index_failures:
        issues.append(
            HealthIssue("index", f"{index_failures} indexing failures")
        )
    fatal = any(
        issue.check in ("snapshot", "documents", "entities")
        for issue in issues
    )
    return GraphHealth(healthy=not issues, issues=issues, stats=stats)


def _input_manifest(backend: MicrosoftGraphRAGBackend) -> dict:
    from graph_memory.sources.adapters import adapt_corpus

    manifest: dict[str, str] = {}
    for artifact in adapt_corpus(backend.corpus_root()):
        filename = artifact.artifact_id.replace("/", "__")
        if not filename.endswith(".txt"):
            filename += ".txt"
        manifest[filename] = artifact.artifact_id
    return manifest
