"""Normalized source artifacts shared by Chapter 3 and GraphRAG inputs.

A normalized artifact carries what the source states about itself —
identifier, source type, location, attributed actor, timestamp, thread —
plus a content hash. Fields that are not stated stay None; adapters must
not infer them (a missing actor is unknown, not "the team").
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

# Closed vocabulary of source types (book §10). The type changes how the
# same proposition is interpreted; it never certifies truth.
SOURCE_TYPES = (
    "chat",
    "session",
    "email",
    "document",
    "decision-record",
    "issue",
    "commit-log",
    "code-diff",
    "benchmark",
    "experiment",
    "database-export",
    "record",
)


@dataclass(frozen=True)
class NormalizedArtifact:
    artifact_id: str  # stable id, e.g. "session-014.md"
    source_type: str  # one of SOURCE_TYPES
    source_uri: str  # path relative to the corpus root
    actor: tuple[str, ...]  # attributed authors, () when unstated
    timestamp: str | None  # stated date, None when unstated
    thread: str | None  # session/discussion grouping, if any
    content: str  # normalized plain-text body
    metadata: dict  # adapter-specific stated facts (status, deciders...)
    content_hash: str  # sha1 of content

    def to_dict(self) -> dict:
        data = asdict(self)
        data["actor"] = list(self.actor)
        return data


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


_DATE_RE = re.compile(r"(?m)^(?:date|effective)[:\s]+(\d{4}-\d{2}-\d{2})")
_CSV_RE = re.compile(r"[,\s]+")
_STRIP_KEYS = (
    "participants:",
    "deciders:",
    "author:",
    "actor:",
    "authors:",
    "status:",
)


def parse_date(text: str) -> str | None:
    match = _DATE_RE.search(text[:800])
    return match.group(1) if match else None


def parse_name_list(value: str) -> tuple[str, ...]:
    names = [n.strip() for n in _CSV_RE.split(value.strip()) if n.strip()]
    # Guard against "and"-joined and dotted-handle forms alike.
    out: list[str] = []
    for name in names:
        if name.lower() == "and":
            continue
        out.append(name)
    return tuple(out)


def header_field(text: str, key: str) -> str | None:
    """Return the value of a `key: value` header line, else None."""
    pattern = re.compile(rf"(?m)^{re.escape(key)}[ \t]+(.+?)[ \t]*$")
    match = pattern.search(text[:800])
    return match.group(1).strip() if match else None
