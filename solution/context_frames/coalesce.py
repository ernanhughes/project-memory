"""Evidence coalescing: remove repetition, never provenance.

The hard rule, inherited from Chapter 7 and Chapter 8: coalescing may
reduce repetition; it may not collapse disagreement, provenance,
temporal boundaries, or support logic.

Three operations, each reversible from the trace:

* **echo folding** -- ``ECHO_OF`` members of a support group stop
  occupying context slots, but their source references join the group's
  item, so the reader still sees where the restatements came from;
* **disagreement preservation** -- a ``REFUTES`` member is never folded.
  It becomes its own item that names what it disagrees with;
* **temporal folding** -- a superseded member of a group whose current
  member is already admitted becomes a note on that item
  (``superseded: old -> new``) rather than a second passage of text.
"""

from __future__ import annotations

from .model import BundleItem, Candidate

COALESCE_VERSION = "source-preserving-v0.1"


def coalesce(admitted: list[Candidate]) -> tuple[list[BundleItem], list[dict]]:
    """Group admitted candidates, returning items and an operation log."""
    items: list[BundleItem] = []
    operations: list[dict] = []
    groups: dict[str, list[Candidate]] = {}
    ungrouped: list[Candidate] = []
    for candidate in admitted:
        key = candidate.unit.claim_key
        if key:
            groups.setdefault(key, []).append(candidate)
        else:
            ungrouped.append(candidate)

    order = [c.unit.claim_key for c in admitted]
    seen: set[str] = set()
    ordered_keys = [k for k in order if k and not (k in seen or seen.add(k))]

    for key in ordered_keys:
        members = groups[key]
        refuters = [c for c in members if c.unit.evidence_role == "refutes"]
        rest = [c for c in members if c.unit.evidence_role != "refutes"]
        if not rest:
            # Only dissent survived the ranking. It stands alone rather than
            # being dropped for having nothing to disagree with.
            for c in refuters:
                items.append(BundleItem(
                    item_id=f"item-{c.unit_id}", text=c.unit.text,
                    members=(c.unit_id,), source_refs=c.unit.source_refs,
                    kind=c.unit.kind, claim_key=key))
                operations.append({"operation": "preserve_dissent_alone",
                                   "claim_key": key,
                                   "item_id": f"item-{c.unit_id}"})
            continue
        current = [c for c in rest if c.unit.valid_until is None]
        superseded = [c for c in rest if c.unit.valid_until is not None]
        echoes = [c for c in current if c.unit.evidence_role == "echo"]
        primary = [c for c in current if c.unit.evidence_role != "echo"]

        if not primary:
            primary, echoes = current, []
        if not primary:
            # Only superseded members survive: keep them, clearly marked.
            primary, superseded = superseded, []

        head = primary[0]
        body = [c.unit.text for c in primary]
        members_ids = tuple(c.unit_id for c in primary + echoes + superseded)
        refs: list[str] = []
        for c in primary + echoes + superseded:
            for ref in c.unit.source_refs:
                if ref not in refs:
                    refs.append(ref)
        note = ""
        if superseded:
            pairs = ", ".join(
                f"{c.unit_id} superseded by {c.unit.superseded_by or head.unit_id}"
                for c in superseded)
            note = f"{pairs} (historical, not current)"
        item = BundleItem(
            item_id=f"item-{head.unit_id}", text="\n".join(body),
            members=members_ids, source_refs=tuple(refs), kind=head.unit.kind,
            claim_key=key, temporal_note=note)
        items.append(item)
        for c in echoes:
            c.coalesced_into = item.item_id
            c.reason_codes.append("ECHO_FOLDED_INTO_GROUP")
        for c in superseded:
            c.coalesced_into = item.item_id
            c.reason_codes.append("SUPERSEDED_FOLDED_AS_NOTE")
        if echoes or superseded or len(primary) > 1:
            operations.append({
                "operation": "group", "claim_key": key,
                "item_id": item.item_id,
                "primary": [c.unit_id for c in primary],
                "echo_folded": [c.unit_id for c in echoes],
                "superseded_folded": [c.unit_id for c in superseded],
                "sources_preserved": len(refs),
            })
        for c in refuters:
            refute_item = BundleItem(
                item_id=f"item-{c.unit_id}", text=c.unit.text,
                members=(c.unit_id,), source_refs=c.unit.source_refs,
                kind=c.unit.kind, claim_key=key,
                conflict_with=(item.item_id,))
            items.append(refute_item)
            operations.append({"operation": "preserve_disagreement",
                               "claim_key": key, "item_id": refute_item.item_id,
                               "conflicts_with": item.item_id})

    for candidate in ungrouped:
        items.append(BundleItem(
            item_id=f"item-{candidate.unit_id}", text=candidate.unit.text,
            members=(candidate.unit_id,),
            source_refs=candidate.unit.source_refs, kind=candidate.unit.kind))
    return items, operations


def passthrough(admitted: list[Candidate]) -> tuple[list[BundleItem], list[dict]]:
    """No coalescing: one item per admitted unit (conditions C0-C5)."""
    return [BundleItem(item_id=f"item-{c.unit_id}", text=c.unit.text,
                       members=(c.unit_id,), source_refs=c.unit.source_refs,
                       kind=c.unit.kind, claim_key=c.unit.claim_key)
            for c in admitted], []
