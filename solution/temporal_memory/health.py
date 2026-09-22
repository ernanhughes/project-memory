"""Structural health report for a temporal log + projection."""

from __future__ import annotations

from .log import EventLog
from .query import MaterializedProjection
from .reducer import projection_digest


def health_report(log: EventLog,
                  materialized: MaterializedProjection | None = None,
                  computed_digest: str | None = None) -> dict:
    by_id = log.by_id()
    seen: dict[str, int] = {}
    dup_ids: list[str] = []
    for record in log.records():
        eid = record["envelope"]["event_id"]
        seen[eid] = seen.get(eid, 0) + 1
        if seen[eid] > 1:
            dup_ids.append(eid)
    report = {
        "events": len(log),
        "sources": sorted({r["envelope"]["source_id"] for r in log.records()}),
        "sequence_gaps": log.gaps(),
        "duplicate_ids": sorted(set(dup_ids)),
        "invalid_intervals": [],
        "unknown_parents": log.unknown_refs(),
        "temporal_causality_violations": log.causality_violations(),
        "last_ingest": log.records()[-1]["received_at"] if log.records() else None,
        "log_digest": log.digest(),
    }
    if materialized is not None:
        digest = projection_digest(materialized.projection)
        report["projection_version"] = materialized.projection_version
        report["projection_digest"] = digest
        report["projection_drift"] = (
            computed_digest is not None and digest != computed_digest)
    report["note"] = ("structural health only: a clean report means the "
                      "history is well-formed, not that it is true")
    return report
