"""Maintained open list: materialized expectation status.

Mirrors Chapter 8's materialized belief: events arrive, affected
expectations are re-evaluated, the projection updates. The canonical
source stays history + expectation records; the list rebuilds from
them with a matching digest.
"""

from __future__ import annotations

import hashlib
import json

from temporal_memory.log import EventLog
from temporal_memory.ordering import temporal_sort

from .config import OpenLoopConfig
from .model import Expectation, StatusReport
from .status import resolve_status


class MaterializedOpenList:
    """Incrementally maintained status projection over a Ch8 event log."""

    def __init__(self, config: OpenLoopConfig | None = None):
        self.config = config or OpenLoopConfig()
        self.expectations: dict[str, Expectation] = {}
        self.statuses: dict[str, StatusReport] = {}
        self.texts: dict[str, str] = {}
        self.update_count = 0

    # -- registration ------------------------------------------------
    def register(self, expectation: Expectation) -> None:
        self.expectations[expectation.expectation_id] = expectation

    def note_text(self, event_id: str, text: str) -> None:
        self.texts[event_id] = text

    # -- ingest ------------------------------------------------------
    def ingest(self, log: EventLog, event_id: str, valid_at: str) -> None:
        """Re-evaluate expectations plausibly affected by one event."""
        event = log.by_id().get(event_id)
        if event is None:
            return
        for exp in self.expectations.values():
            if exp.subject == event.subject or exp.desired.subject == event.subject:
                self.statuses[exp.expectation_id] = resolve_status(
                    exp, log, valid_at, config=self.config, texts=self.texts)
        self.update_count += 1

    def refresh_all(self, log: EventLog, valid_at: str,
                    known_at: str | None = None) -> None:
        for exp in self.expectations.values():
            report = resolve_status(exp, log, valid_at, known_at,
                                    config=self.config, texts=self.texts)
            report.last_verified_at = valid_at
            self.statuses[exp.expectation_id] = report

    def list_open(self, scope: str | None = None) -> list[StatusReport]:
        out = [r for eid, r in self.statuses.items()
               if r.status == "OPEN"
               and (scope is None
                    or self.expectations[eid].scope == scope)]
        return sorted(out, key=lambda r: r.expectation_id)

    # -- rebuild ------------------------------------------------------
    def rebuild(self, log: EventLog, valid_at: str) -> None:
        ordered = temporal_sort(log.events(), log.by_id())
        self.statuses = {}
        for exp in self.expectations.values():
            self.statuses[exp.expectation_id] = resolve_status(
                exp, log, valid_at, config=self.config, texts=self.texts)
        self._rebuild_order = [e.event_id for e in ordered]

    def digest(self) -> str:
        canonical = {eid: (r.status, r.closing_evidence)
                     for eid, r in sorted(self.statuses.items())}
        return hashlib.sha256(
            json.dumps(canonical, sort_keys=True,
                       default=list).encode()).hexdigest()[:16]
