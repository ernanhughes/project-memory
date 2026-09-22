"""Provenance mapping over a built GraphRAG index.

The target chain (book §9):

```text
derived memory (entity / relationship / claim / community)
    ↓ text_unit_ids
text unit
    ↓ document_ids
source document (input filename)
    ↓ manifest
canonical artifact (artifact_id in the Chapter 3 corpus)
```

Any link that cannot be walked is recorded as a mapping failure, not
silently dropped. A derived object with no path back to a canonical
artifact is an orphan: usable as a hypothesis, never as evidence.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))

from graph_memory.graphrag_backend.backend import GraphSnapshot  # noqa: E402
from graph_memory.graphrag_backend.microsoft import (  # noqa: E402
    MicrosoftGraphRAGBackend,
)


@dataclass
class ProvenanceChain:
    derived_kind: str  # entity | relationship | claim | community
    derived_id: str
    derived_name: str
    text_units: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    broken_links: list[str] = field(default_factory=list)

    @property
    def is_orphan(self) -> bool:
        return not self.artifacts

    def to_dict(self) -> dict:
        return {
            "derived_kind": self.derived_kind,
            "derived_id": self.derived_id,
            "derived_name": self.derived_name,
            "text_units": self.text_units,
            "documents": self.documents,
            "artifacts": self.artifacts,
            "broken_links": self.broken_links,
            "is_orphan": self.is_orphan,
        }


@dataclass
class ProvenanceReport:
    chains: list[ProvenanceChain] = field(default_factory=list)

    def orphan_rate(self, kind: str | None = None) -> float | None:
        selected = [
            c for c in self.chains if kind is None or c.derived_kind == kind
        ]
        if not selected:
            return None
        orphaned = sum(1 for c in selected if c.is_orphan)
        return orphaned / len(selected)

    def to_dict(self) -> dict:
        return {
            "chains": [c.to_dict() for c in self.chains],
            "orphan_rates": {
                kind: self.orphan_rate(kind)
                for kind in ("entity", "relationship", "claim", "community")
            },
            "overall_orphan_rate": self.orphan_rate(),
        }


def _input_filename_to_artifact(filename: str, manifest: dict) -> str | None:
    """Map a GraphRAG document title back to the canonical artifact id."""
    if filename in manifest:
        return manifest[filename]
    stem = filename[:-4] if filename.endswith(".txt") else filename
    return manifest.get(stem, manifest.get(stem + ".txt"))


def build_report(
    backend: MicrosoftGraphRAGBackend,
    snapshot: GraphSnapshot,
    manifest: dict,
) -> ProvenanceReport:
    """Walk every derived object back to canonical artifacts."""
    unit_sources = backend.text_unit_sources()
    report = ProvenanceReport()

    def resolve(text_units: list[str]) -> tuple[list[str], list[str], list[str]]:
        docs: list[str] = []
        artifacts: list[str] = []
        broken: list[str] = []
        for unit in text_units:
            unit_docs = unit_sources.get(unit)
            if not unit_docs:
                broken.append(f"text_unit:{unit}")
                continue
            for doc in unit_docs:
                if doc not in docs:
                    docs.append(doc)
                artifact = _input_filename_to_artifact(doc, manifest)
                if artifact is None:
                    broken.append(f"document:{doc}")
                elif artifact not in artifacts:
                    artifacts.append(artifact)
        return docs, artifacts, broken

    for entity in snapshot.entities:
        docs, artifacts, broken = resolve(entity.source_text_units)
        report.chains.append(
            ProvenanceChain(
                derived_kind="entity",
                derived_id=entity.entity_id,
                derived_name=entity.name,
                text_units=list(entity.source_text_units),
                documents=docs,
                artifacts=artifacts,
                broken_links=broken,
            )
        )
    for rel in snapshot.relationships:
        docs, artifacts, broken = resolve(rel.source_text_units)
        report.chains.append(
            ProvenanceChain(
                derived_kind="relationship",
                derived_id=rel.relationship_id,
                derived_name=f"{rel.source} -> {rel.target}",
                text_units=list(rel.source_text_units),
                documents=docs,
                artifacts=artifacts,
                broken_links=broken,
            )
        )
    for claim in snapshot.claims:
        docs, artifacts, broken = resolve(claim.source_text_units)
        report.chains.append(
            ProvenanceChain(
                derived_kind="claim",
                derived_id=claim.claim_id,
                derived_name=claim.subject or claim.description[:80],
                text_units=list(claim.source_text_units),
                documents=docs,
                artifacts=artifacts,
                broken_links=broken,
            )
        )
    for community in snapshot.communities:
        docs, artifacts, broken = resolve(community.source_text_units)
        report.chains.append(ProvenanceChain(
            derived_kind="community", derived_id=community.community_id,
            derived_name=community.title, text_units=list(community.source_text_units),
            documents=docs, artifacts=artifacts, broken_links=broken))
    return report
