"""Structural health for expectations + open list (never semantic truth)."""

from __future__ import annotations

from temporal_memory.log import EventLog

from .materialized import MaterializedOpenList
from .model import Expectation


def health_report(expectations: list[Expectation], log: EventLog,
                  open_list: MaterializedOpenList | None = None) -> dict:
    seen: dict[tuple[str, str, str], list[str]] = {}
    for exp in expectations:
        key = (exp.subject, exp.desired.predicate, exp.desired.target)
        seen.setdefault(key, []).append(exp.expectation_id)
    duplicates = {f"{k}": v for k, v in seen.items() if len(v) > 1}
    closing_targets: set[str] = set()
    for event in log.events():
        payload = dict(event.payload)
        if payload.get("open_loops.role") in ("complete", "cancel", "supersede"):
            closing_targets.add(payload.get("open_loops.target", ""))
    known = {exp.expectation_id for exp in expectations}
    report = {
        "expectations": len(expectations),
        "open": 0,
        "satisfied": 0,
        "cancelled": 0,
        "superseded": 0,
        "unknown": 0,
        "without_opening_evidence": [
            exp.expectation_id for exp in expectations
            if not exp.opening_evidence],
        "closing_events_without_expectation": sorted(
            closing_targets - known),
        "duplicate_expectations": duplicates,
        "history_gaps_affecting": log.gaps(),
        "stale_unverified_open": [],
    }
    if open_list is not None:
        for eid, status in open_list.statuses.items():
            key = status.status.lower()
            if key in report:
                report[key] += 1
            if status.status == "OPEN" and status.last_verified_at is None:
                report["stale_unverified_open"].append(eid)
    report["note"] = ("structural health only: a clean report means the "
                      "open list is well-formed, not that it is right")
    return report
