"""C6 trust admission over sim views: adaptation, not policy.

This module contains NO trust policy logic. It maps simulator views
plus probe metadata to trust_policy Units, calls the imported
Chapter 17 gate (trust-policy-v1, frozen in the memory repo), and
renders admitted sets. Every admission decision — including its
gaps — belongs to the imported policy; a gap found here is reported
as a trust-policy finding for T7, never silently patched here.

Probe metadata (per probe, documented at the call site, ledger
untouched):

* revoked: record keys designated revoked for the probe.
* refutes: (a, b) pairs relating units as mutual refutations.
* claims: unit_id -> normalized claim overrides (constructed units).
* restricted: unit_id -> scope for restriction probes (unused: no
  restricted fixtures in v0.1 scope; reserved).

Unit identity: ledger-backed views use record keys (so
derived_from refs resolve); constructed views use display ids.
"""

from __future__ import annotations

import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_PM_ROOT = _THIS.parents[1]
_MEMORY_SOLUTION = _PM_ROOT.parent / "memory" / "solution"
if str(_MEMORY_SOLUTION) not in sys.path:
    sys.path.insert(0, str(_MEMORY_SOLUTION))

from context_frames import trust_policy as tp  # noqa: E402

TRUST_POLICY_VERSION = tp.TRUST_POLICY_VERSION
assert TRUST_POLICY_VERSION == "trust-policy-v1.1", TRUST_POLICY_VERSION

LEVELS = ("S1", "S2", "S3", "FULL")


def units_from_views(views: list[dict], records_by_display: dict,
                     records_by_key: dict,
                     meta: dict | None = None) -> list:
    """Map rendered views to trust Units in display-id namespace.

    unit_id is always the display id (split decisions share one
    record key across two artifacts, so record keys collide).
    derived_from refs resolve through record keys to primary display
    ids. Probe metadata (revoked/refutes/claims/constructed) is also
    keyed by display id. Constructed views (absent from records)
    take kind/refs from meta["constructed"].
    """
    meta = meta or {}
    revoked = set(meta.get("revoked", ()))
    refutes_map: dict[str, list[str]] = {}
    for a, b in meta.get("refutes", ()):
        refutes_map.setdefault(a, []).append(b)
        refutes_map.setdefault(b, []).append(a)
    constructed = meta.get("constructed", {})
    claims = meta.get("claims", {})

    def display_of(key: str) -> str:
        record = records_by_key.get(key)
        if record is not None and record.display_id:
            return record.display_id
        return key

    units = []
    for view in views:
        did = view["display_id"]
        record = records_by_display.get(did)
        if record is not None:
            derived = tuple(display_of(k) for k in
                            (record.derived_from or ()))
            units.append(tp.Unit(
                unit_id=did, kind=record.kind,
                project=view.get("project", "main"), date=record.date,
                text=view.get("body", ""), claim=record.content,
                artifact_kind=record.artifact_kind or "session",
                valid_from=record.valid_from or "",
                valid_until=record.valid_until or "",
                derived_from=derived,
                refuted_by=tuple(refutes_map.get(did, ())),
                revoked=did in revoked,
                restricted_to=""))
        else:
            spec = constructed.get(did, {})
            units.append(tp.Unit(
                unit_id=did,
                kind=spec.get("kind", "evidence"),
                project=view.get("project", "main"),
                date=view.get("date", ""),
                text=view.get("body", ""),
                claim=claims.get(did, spec.get("claim", "")),
                artifact_kind=spec.get("artifact_kind", "session"),
                valid_from="", valid_until="",
                derived_from=tuple(spec.get("derived_from", ())),
                refuted_by=tuple(refutes_map.get(did, ())),
                revoked=did in revoked,
                restricted_to=""))
    return units


def task_packet(task, consequential: bool = True):
    return tp.TaskPacket(task.task_id, task.text, task.as_of,
                         getattr(task, "project", "main"), "agent",
                         consequential)


def admit(units: list, task, level: str) -> dict:
    """Run one imported policy level. Returns unit_id -> Admission."""
    result = tp.apply_policy(units, task, level)
    return result.admissions


def admitted_set(admissions: dict) -> set[str]:
    return {uid for uid, a in admissions.items() if a.verdict == "admit"}
