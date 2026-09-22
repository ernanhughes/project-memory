"""Frame-evidence extraction: ledger reconciliation to establishment hints.

This module derives establishment-relevant evidence for a frame subject
from a ``LineageGraph`` plus a ``ReconciliationSet``. It is a pure
derivation layer: it returns hint records in the gate's vocabulary and
changes no gate behaviour. The frame/policy layer is built on top of
these tested semantics in a later step; nothing here calls into
``frame_safety`` and nothing here ranks, admits, or excludes.

Hint vocabulary (subset of the establishment classes):

* ``corroborated`` — a resolving SAME_EVENT/COMPLETES record from
  ledger-level authority holds at as_of.
* ``weak`` — the resolving record holds but its authority is a single
  agent rather than the ledger or an author merge.
* ``stale`` — the record is stale or was invalidated (validity ended,
  revocation/contradiction/supersession inside the window).
* ``conflicting`` — the subjects contradict and the record claims to
  resolve. Refused upstream; surfaced here as conflict evidence.
* ``unknown`` — cross-scope without licence (quarantined), or no
  resolving record mentions the subject at all.

Every hint names its basis (reconciliation ids) and reason, so a
consumer can audit the derivation instead of trusting the label.
"""

from __future__ import annotations

from evidence_lineage import reconciliation as R
from evidence_lineage.lineage import LineageGraph

LEDGER_AUTHORITIES = ("author-merge", "ledger")

HINTS = ("corroborated", "weak", "stale", "conflicting", "unknown")


def establishment_hints_for(graph: LineageGraph, rset: R.ReconciliationSet,
                            subject: str, as_of: str,
                            later: tuple[R.LaterEvent, ...] = ()) -> list[dict]:
    """Derive establishment hints for one subject. Deterministic."""
    hints = []
    for rec_id in sorted(rset.records):
        rec = rset.records[rec_id]
        if subject not in (rec.subject_a, rec.subject_b):
            continue
        out = rset.resolve(graph, rec_id, as_of, later=later)
        hint = _hint_for(out, rec)
        if hint is None:
            continue
        hints.append({"subject": subject, "hint": hint,
                      "basis": [rec_id], "authority": rec.authority,
                      "relationship": rec.relationship.value,
                      "reason": out["detail"]})
    return hints


def _hint_for(out: dict, rec: R.Reconciliation) -> str | None:
    res = out["resolution"]
    if res == "correspondence_only":
        return None
    if res == "resolved":
        if rec.authority in LEDGER_AUTHORITIES:
            return "corroborated"
        return "weak"
    if res in ("stale", "invalidated"):
        return "stale"
    if res == "conflict":
        return "conflicting"
    if res == "cross_scope":
        return "unknown"
    raise ValueError(f"unknown resolution {res!r}")
