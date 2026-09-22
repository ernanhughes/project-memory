"""Per-type adapters from baseline sources to normalized artifacts.

Each adapter reads only what its source type states. Type detection reuses
the Chapter 3 classifier (``memory_baseline.ingest.artifact_type``) and
refines it where filenames carry stronger signals (benchmarks and
experiments are documents with measurements, not prose).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))

from memory_baseline import ingest as baseline_ingest  # noqa: E402

from .normalize import (  # noqa: E402
    NormalizedArtifact,
    header_field,
    parse_date,
    parse_name_list,
    sha1,
)

_COMMIT_LINE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s{2,}(?P<message>.+?)\s*$"
)


def refine_type(source_id: str, baseline_type: str, content: str) -> str:
    """Map the baseline artifact type onto the source-type vocabulary."""
    name = source_id.lower()
    if baseline_type == "session" or name.startswith("session-"):
        return "session"
    if baseline_type == "decision-record":
        return "decision-record"
    if baseline_type == "commit-log":
        return "commit-log"
    if baseline_type == "issue":
        return "issue"
    if "benchmark" in name or "experiment" in name:
        kind = "benchmark" if "benchmark" in name else "experiment"
        return kind
    if name.startswith("production-") or "database" in name:
        return "database-export"
    if baseline_type in ("document", "record", "config", "code"):
        return "document" if baseline_type != "record" else "record"
    return "document"


def adapt_session(source: baseline_ingest.Source) -> NormalizedArtifact:
    participants = header_field(source.content, "participants:")
    actors = parse_name_list(participants) if participants else ()
    thread = source.source_id.split(".")[0]
    return NormalizedArtifact(
        artifact_id=source.source_id,
        source_type="session",
        source_uri=source.source_id,
        actor=actors,
        timestamp=parse_date(source.content),
        thread=thread,
        content=source.content.strip(),
        metadata={"participants": list(actors)},
        content_hash=source.content_hash,
    )


def adapt_decision_record(
    source: baseline_ingest.Source,
) -> NormalizedArtifact:
    deciders = header_field(source.content, "deciders:")
    actors = parse_name_list(deciders) if deciders else ()
    status = header_field(source.content, "status:")
    return NormalizedArtifact(
        artifact_id=source.source_id,
        source_type="decision-record",
        source_uri=source.source_id,
        actor=actors,
        timestamp=parse_date(source.content),
        thread=None,
        content=source.content.strip(),
        metadata={
            "deciders": list(actors),
            "status": status,
        },
        content_hash=source.content_hash,
    )


def adapt_commit_log(source: baseline_ingest.Source) -> list[NormalizedArtifact]:
    """One artifact per commit entry: each entry is its own dated record."""
    entries: list[NormalizedArtifact] = []
    for ordinal, line in enumerate(source.content.splitlines()):
        match = _COMMIT_LINE_RE.match(line.rstrip())
        if not match:
            continue
        message = match.group("message").strip()
        artifact_id = f"{source.source_id}#L{ordinal + 1}"
        entries.append(
            NormalizedArtifact(
                artifact_id=artifact_id,
                source_type="commit-log",
                source_uri=source.source_id,
                actor=(),
                timestamp=match.group("date"),
                thread=None,
                content=f"{match.group('date')}  {message}",
                metadata={"log_line": ordinal + 1},
                content_hash=sha1(message),
            )
        )
    return entries


def adapt_generic(
    source: baseline_ingest.Source, source_type: str
) -> NormalizedArtifact:
    return NormalizedArtifact(
        artifact_id=source.source_id,
        source_type=source_type,
        source_uri=source.source_id,
        actor=(),
        timestamp=parse_date(source.content),
        thread=None,
        content=source.content.strip(),
        metadata={},
        content_hash=source.content_hash,
    )


def adapt_source(source: baseline_ingest.Source) -> list[NormalizedArtifact]:
    """Adapt one baseline source into one or more normalized artifacts."""
    source_type = refine_type(
        source.source_id, source.artifact_type, source.content
    )
    if source_type == "session":
        return [adapt_session(source)]
    if source_type == "decision-record":
        return [adapt_decision_record(source)]
    if source_type == "commit-log":
        return adapt_commit_log(source)
    return [adapt_generic(source, source_type)]


def adapt_corpus(root: Path) -> list[NormalizedArtifact]:
    """Adapt every discoverable source under root, deterministically."""
    artifacts: list[NormalizedArtifact] = []
    for path in baseline_ingest.discover(root):
        source = baseline_ingest.parse(path, root)
        if source is None:
            continue
        artifacts.extend(adapt_source(source))
    artifacts.sort(key=lambda a: a.artifact_id)
    return artifacts


def write_input_docs(artifacts: list[NormalizedArtifact], input_dir: Path) -> dict:
    """Write one text file per artifact for GraphRAG text input.

    Filenames are the artifact ids with path separators flattened, so the
    GraphRAG document table maps back onto canonical artifact ids for
    provenance (book §9). Returns the manifest {filename: artifact_id}.
    """
    input_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for artifact in artifacts:
        filename = artifact.artifact_id.replace("/", "__")
        if not filename.endswith(".txt"):
            filename += ".txt"
        # Provenance header, v2 rendering: only stated fields are emitted.
        # An earlier rendering wrote "ACTOR: unknown" / "DATE: unknown"
        # lines, which the extractor reified into UNKNOWN-person and
        # date-as-event entities. Absence stays absent.
        lines = [
            f"ARTIFACT: {artifact.artifact_id}",
            f"SOURCE_TYPE: {artifact.source_type}",
        ]
        if artifact.actor:
            lines.append(f"ACTOR: {', '.join(artifact.actor)}")
        if artifact.timestamp:
            lines.append(f"DATE: {artifact.timestamp}")
        if artifact.thread:
            lines.append(f"THREAD: {artifact.thread}")
        header = "\n".join(lines) + "\n\n"
        (input_dir / filename).write_text(
            header + artifact.content, encoding="utf-8"
        )
        manifest[filename] = artifact.artifact_id
    return manifest
