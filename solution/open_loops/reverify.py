"""Re-verification: standing maintenance against compounding error.

Status errors persist across runs where belief errors merely repeat, so
the open list needs re-examination with provenance: what was checked,
when, against which history. Re-verification never invents closures; it
re-runs the resolver over newer history and records the footprint.
"""

from __future__ import annotations

from temporal_memory.log import EventLog

from .config import OpenLoopConfig
from .materialized import MaterializedOpenList
from .model import Expectation, StatusReport
from .status import resolve_status


def reverify(expectation: Expectation, log: EventLog, valid_at: str,
             config: OpenLoopConfig | None = None,
             texts: dict[str, str] | None = None) -> StatusReport:
    """One controlled re-verification pass over a single expectation."""
    report = resolve_status(expectation, log, valid_at,
                            config=config or OpenLoopConfig(),
                            texts=texts or {})
    report.last_verified_at = valid_at
    return report


def run_reverification(open_list: MaterializedOpenList, log: EventLog,
                       valid_at: str) -> dict[str, int]:
    """Re-check every currently-open expectation; return repair counts."""
    before = {eid for eid, r in open_list.statuses.items()
              if r.status == "OPEN"}
    open_list.refresh_all(log, valid_at)
    after = {eid for eid, r in open_list.statuses.items()
             if r.status == "OPEN"}
    repaired = before - after
    return {"re-examined": len(before), "repaired": len(repaired),
            "still_open": len(after)}
