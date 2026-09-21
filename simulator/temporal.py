"""C3 structured/temporal memory: validity filtering (next5 sequence).

The mechanism owns exactly one idea: at a standpoint, superseded
records are not current guidance. It excludes views backing records
with valid_until <= as_of and preserves everything else in original
order. It must NOT solve anything else:

* cross-project authority: out of scope (C4 owns scope);
* poison/instruction content: untouched (C6 owns trust);
* revocation: untouched (no revocation representation exists yet;
  expiry by valid_until is the only temporal signal).

Pre-registered expectations on the frozen 11-task family: WS topics
lose their stale-only content (harm source removed); WC topics keep
the current decision (no damage); WX/WP/WR pass through unchanged
(their hazards are non-temporal by construction).
"""

from __future__ import annotations


def superseded_display_ids(ledger, as_of: str) -> set[str]:
    """Display ids whose record validity ended on or before as_of."""
    out: set[str] = set()
    for record in ledger.records:
        if record.valid_until is not None and record.valid_until <= as_of:
            if record.display_id:
                out.add(record.display_id)
            if record.second_display_id:
                out.add(record.second_display_id)
    return out


def temporal_filter(views: list[dict], ledger, as_of: str) -> list[dict]:
    """Exclude superseded views, preserve order. Nothing else."""
    dropped = superseded_display_ids(ledger, as_of)
    return [v for v in views if v["display_id"] not in dropped]
