"""Internal ID assignment (H1 pipeline stage 3).

gen-NNNNNN IDs are monotonic in ingestion order and carry no scenario or
date signal beyond order itself. Ingestion order is chronological by
artifact date with a seeded tiebreak, so equal-dated artifacts cannot leak
kind information through filename order. Display IDs stay in content.
"""

from __future__ import annotations

import random


def assign_ids(
    display_ids_in_ingestion_order: list[str],
) -> dict[str, str]:
    """Map display ID -> gen-NNNNNN internal ID, monotonic in given order."""
    mapping: dict[str, str] = {}
    for i, display_id in enumerate(display_ids_in_ingestion_order, start=1):
        mapping[display_id] = f"gen-{i:06d}"
    return mapping


def ingestion_order(
    artifacts: list, rng: random.Random
) -> list:
    """Seeded-shuffle ingestion order.

    Ingestion order is deliberately arbitrary (a crawler's order), not
    chronological: chronological order correlates with scenario position
    (proposals before decisions), which would make file order predictive
    of record kind. Shuffling removes the signal by construction while
    staying fully deterministic given the seed.
    """
    ordered = list(artifacts)
    rng.shuffle(ordered)
    return ordered


def filename_for(internal_id: str) -> str:
    return f"{internal_id}.md"
