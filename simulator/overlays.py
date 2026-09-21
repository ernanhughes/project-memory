"""Ledger overlays: in-memory interventions (T1, PART XVI subset).

Overlays copy the ledger, apply one surgical change, and revalidate.
Frozen fixtures are never mutated; every overlay records what changed
so runs stay attributable. Supported ops: remove a record by key (and
drop edges pointing at it), add a record.
"""

from __future__ import annotations

import dataclasses

from generator.schema import Ledger


def remove_record(ledger: Ledger, key: str) -> Ledger:
    kept = []
    for record in ledger.records:
        if record.key == key:
            continue
        kept.append(dataclasses.replace(
            record,
            supersedes=tuple(k for k in record.supersedes if k != key),
            supported_by=tuple(k for k in record.supported_by if k != key),
            derived_from=tuple(k for k in record.derived_from if k != key)))
    return Ledger(kept).validate()


def add_record(ledger: Ledger, record) -> Ledger:
    return Ledger(list(ledger.records) + [record]).validate()
