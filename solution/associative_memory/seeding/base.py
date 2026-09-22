"""How a cue enters the graph.

Every propagation strategy in this package begins from a set of seeded
nodes. A seeder that lands on the wrong nodes makes the comparison
between propagation strategies meaningless, so seeding is a separate
interface with its own measurement (book §13), and the HippoRAG 2 result
— that changing seeding alone moved multi-hop recall substantially — is
the reason it is not folded into the retriever.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9_.\-]+")

# Words that carry no cue information. Deliberately short: an aggressive
# stop list hides seeding failures rather than fixing them.
STOPWORDS = frozenset(
    """
    a an and are as at be been but by did do does for from had has have
    how in into is it its of on or should that the their them then there
    these they this to was we were what when where which who why will
    with would you your
    """.split()
)


def tokenise(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN.findall(text.lower())
        if token not in STOPWORDS and len(token) > 1
    ]


@dataclass(frozen=True)
class Seed:
    """One entry point into the graph, with the reason it was chosen."""

    node_id: str
    score: float
    method: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "score": round(self.score, 6),
            "method": self.method,
            "evidence": list(self.evidence),
        }


class Seeder(Protocol):
    """Map a cue onto seeded nodes with initial activation."""

    name: str

    def seed(self, cue: str, graph) -> list[Seed]:
        ...


def node_text(node) -> str:
    """The text a seeder matches against."""
    return " ".join(
        part
        for part in (node.label, node.description, " ".join(node.terms))
        if part
    )


def top_seeds(
    scored: dict[str, tuple[float, tuple[str, ...]]],
    method: str,
    top_k: int,
    min_score: float,
) -> list[Seed]:
    ranked = sorted(
        scored.items(), key=lambda item: (-item[1][0], item[0])
    )
    seeds: list[Seed] = []
    for node_id, (score, evidence) in ranked:
        if score < min_score or len(seeds) >= top_k:
            break
        seeds.append(
            Seed(node_id=node_id, score=score, method=method, evidence=evidence)
        )
    return seeds
