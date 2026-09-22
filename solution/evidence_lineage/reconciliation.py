"""Ledger reconciliation as evidence (Chapters 7-8 grounding).

A reconciliation records that two representations were deliberately
related: same underlying event, a completion closing an obligation, or
mere correspondence. It preserves both original records plus the
relationship, the standpoint (when asserted), the authority that
asserted it, and whether it resolves a conflict or only records
correspondence.

The structural rule this module enforces, and the reason it exists:

```text
record A
record B
RECONCILIATION(A, B)
```

must NOT automatically become ``A == B == current truth`` unless the
evidence and temporal rules actually establish that. Resolving a
reconciliation answers whether the RELATIONSHIP holds (same event?
completed? correspondent?) at an as_of date. It never answers whether
the records' CONTENT is true. Content truth stays where Chapters 7
(verification against support) and 8 (validity intervals, supersession)
put it; this module does not touch either path.

Relationship kinds (each has exactly one meaning):

* SAME_EVENT — both records describe one underlying event (e.g. an
  intent record and the commit that silently completes it).
* COMPLETES — subject A closes an obligation opened by subject B.
* CORRESPONDENCE — the records correspond (shared topic, shared
  episode) without any sameness or closure claim. Correspondence can
  never resolve, structurally: ``resolves_conflict`` is rejected for
  it at add time.

Resolution statuses (``resolve`` is total: every call returns one):

* CORRESPONDENCE_ONLY — the record is correspondence, or its flag is
  off. No relationship claim is evaluated for truth.
* RESOLVED — the relationship holds at as_of. Content truth untouched.
* STALE — a subject's validity interval ended before as_of.
* CONFLICT — the subjects contradict each other and the record claims
  to resolve. Refused, not merged.
* INVALIDATED — as_of precedes the standpoint, or a later revocation
  or contradiction names a subject inside (standpoint, as_of].
* CROSS_SCOPE — the subjects live in different projects and the
  authority is not the explicit cross-scope licence (``author-merge``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .lineage import LineageGraph

DATE_RE_LEN = 10  # ISO YYYY-MM-DD prefix compare; full datetimes compare too

#: Authority string that may relate records across project scope.
#: Anything else relating cross-project subjects is quarantined, not
#: merged: scope isolation is the default, explicit licence the
#: exception.
CROSS_SCOPE_AUTHORITY = "author-merge"

DEFAULT_PROJECT = "main"


class Relationship(str, Enum):
    SAME_EVENT = "same_event"
    COMPLETES = "completes"
    CORRESPONDENCE = "correspondence"


class Resolution(str, Enum):
    CORRESPONDENCE_ONLY = "correspondence_only"
    RESOLVED = "resolved"
    STALE = "stale"
    CONFLICT = "conflict"
    INVALIDATED = "invalidated"
    CROSS_SCOPE = "cross_scope"


@dataclass(frozen=True)
class Reconciliation:
    """One deliberate relating of two records.

    ``standpoint`` is the ISO date the relating was asserted.
    ``authority`` names who asserted it (``author-merge``, ``ledger``,
    ``agent:<id>`` ...). ``resolves_conflict`` states the ambition:
    True claims the relationship settles something; False records
    correspondence only. ``source_refs`` points at the evidence that
    licensed the relating (session ids, merge refs).
    """

    rec_id: str
    subject_a: str
    subject_b: str
    relationship: Relationship
    standpoint: str
    authority: str
    source_refs: tuple[str, ...] = ()
    resolves_conflict: bool = False
    note: str = ""


@dataclass(frozen=True)
class LaterEvent:
    """Something that happened after a standpoint and may bear on it.

    ``kind`` is ``revocation`` (a subject's source was revoked),
    ``contradiction`` (new evidence against a subject), or
    ``supersession`` (a subject's claim was superseded). ``date`` is
    ISO; only events inside (standpoint, as_of] affect a resolution.
    """

    date: str
    kind: str  # revocation | contradiction | supersession
    subject: str
    note: str = ""


@dataclass
class ReconciliationSet:
    """Validated container. Add-time rules keep unassertable relations
    out; resolve-time rules keep truth collapse out."""

    records: dict[str, Reconciliation] = field(default_factory=dict)

    def add(self, rec: Reconciliation, graph: LineageGraph) -> None:
        if rec.rec_id in self.records:
            raise ValueError(f"duplicate reconciliation {rec.rec_id!r}")
        if rec.subject_a == rec.subject_b:
            raise ValueError("reconciliation needs two distinct subjects")
        for sid in (rec.subject_a, rec.subject_b):
            if sid not in graph.nodes:
                raise ValueError(f"unknown subject {sid!r}")
        for sid in (rec.subject_a, rec.subject_b):
            born = _payload(graph, sid, "date")
            if born and rec.standpoint < born:
                raise ValueError(
                    f"{rec.rec_id!r}: standpoint {rec.standpoint} precedes "
                    f"subject {sid!r} dated {born}")
        if not rec.authority:
            raise ValueError(f"{rec.rec_id!r}: authority is required")
        if (rec.relationship == Relationship.CORRESPONDENCE
                and rec.resolves_conflict):
            raise ValueError(
                f"{rec.rec_id!r}: correspondence never resolves; "
                "record the ambition as correspondence only")
        self.records[rec.rec_id] = rec

    def resolve(self, graph: LineageGraph, rec_id: str, as_of: str,
                later: tuple[LaterEvent, ...] = ()) -> dict:
        """Resolve a relationship at an as_of date. Total function."""
        rec = self.records[rec_id]
        if not rec.resolves_conflict:
            return _status(Resolution.CORRESPONDENCE_ONLY, rec,
                           "correspondence recorded; nothing evaluated")
        if as_of < rec.standpoint:
            return _status(Resolution.INVALIDATED, rec,
                           f"as_of {as_of} precedes standpoint "
                           f"{rec.standpoint}")
        for sid in (rec.subject_a, rec.subject_b):
            if _payload(graph, sid, "contradicts") in (
                    rec.subject_a, rec.subject_b):
                return _status(Resolution.CONFLICT, rec,
                               f"subjects contradict; refused, not merged")
        if _projects_differ(graph, rec):
            if rec.authority != CROSS_SCOPE_AUTHORITY:
                return _status(Resolution.CROSS_SCOPE, rec,
                               "cross-project relating without explicit "
                               "licence; quarantined")
        for sid in (rec.subject_a, rec.subject_b):
            until = _payload(graph, sid, "valid_until")
            if until and until < as_of:
                return _status(Resolution.STALE, rec,
                               f"subject {sid!r} validity ended {until}")
        for ev in later:
            if not (rec.standpoint < ev.date <= as_of):
                continue
            if ev.subject not in (rec.subject_a, rec.subject_b):
                continue
            if ev.kind in ("revocation", "contradiction", "supersession"):
                return _status(Resolution.INVALIDATED, rec,
                               f"{ev.kind} of {ev.subject!r} at {ev.date}")
        return _status(Resolution.RESOLVED, rec,
                       f"{rec.relationship.value} holds at {as_of}; "
                       "content truth untouched")


def _payload(graph: LineageGraph, node_id: str, key: str) -> str:
    for k, v in graph.nodes[node_id].payload:
        if k == key:
            return v
    return ""


def _projects_differ(graph: LineageGraph, rec: Reconciliation) -> bool:
    pa = _payload(graph, rec.subject_a, "project") or DEFAULT_PROJECT
    pb = _payload(graph, rec.subject_b, "project") or DEFAULT_PROJECT
    return pa != pb


def _status(resolution: Resolution, rec: Reconciliation,
            detail: str) -> dict:
    return {"rec_id": rec.rec_id, "resolution": resolution.value,
            "relationship": rec.relationship.value,
            "resolves_conflict": rec.resolves_conflict,
            "standpoint": rec.standpoint, "authority": rec.authority,
            "detail": detail}
