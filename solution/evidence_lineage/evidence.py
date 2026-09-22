"""Evidence references and support groups.

A claim is licensed by *groups* of evidence, not by a count of
citations. Semantics (minimal-evidence-group style):

* inside one group: conjunction — every member is necessary;
* across groups: disjunction — any fully satisfied group suffices.

A single-member group is ordinary single-source support. An echo is
never a group member: repetition is derivation, not corroboration.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvidenceRef:
    """A stable link back to inspectable source material."""

    artifact_id: str
    span_id: str
    quote: str
    source_type: str = "raw"
    # Source types: raw (Chapter 3 artifact), derived (Ch4/5 output),
    # context (retrieved memory), reader (generated output).


@dataclass(frozen=True)
class SupportEdge:
    """One proposed SUPPORTED_BY relation with its own provenance."""

    claim_id: str
    evidence_id: str  # node id in the lineage graph (usually a span)
    group_id: str
    extractor: str = "fixture"
    extractor_version: str = "ledger-deterministic-v0.1"
    # Extraction confidence: confidence the edge was correctly
    # extracted — never the probability the claim is true.
    extraction_confidence: float = 1.0
    licensed_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupportGroup:
    """One sufficient conjunction of evidence for a claim."""

    id: str
    claim_id: str
    members: tuple[str, ...]  # evidence node ids, all necessary
    kind: str = "conjunctive"


@dataclass
class ClaimSupport:
    """All support structure for one claim."""

    claim_id: str
    groups: list[SupportGroup] = field(default_factory=list)
    edges: list[SupportEdge] = field(default_factory=list)

    def group(self, group_id: str) -> SupportGroup | None:
        for group in self.groups:
            if group.id == group_id:
                return group
        return None


def group_status(group: SupportGroup,
                 entails: set[tuple[str, str]]) -> str:
    """Satisfaction of one conjunction against entailment truth.

    ``entails`` holds (claim_id, evidence_id) pairs known to support.
    Returns satisfied / partial / unsatisfied.
    """
    hits = sum(1 for m in group.members
               if (group.claim_id, m) in entails)
    if hits == len(group.members) and hits > 0:
        return "satisfied"
    if hits > 0:
        return "partial"
    return "unsatisfied"


def claim_support_status(support: ClaimSupport,
                         entails: set[tuple[str, str]]) -> dict:
    """Disjunction over groups: any satisfied group licenses the claim."""
    states = [group_status(g, entails) for g in support.groups]
    if any(s == "satisfied" for s in states):
        overall = "FULLY_SUPPORTED"
    elif any(s == "partial" for s in states):
        overall = "PARTIALLY_SUPPORTED"
    else:
        overall = "NOT_SUPPORTED"
    satisfied_groups = [g.id for g, s in zip(support.groups, states)
                        if s == "satisfied"]
    return {
        "claim_id": support.claim_id,
        "status": overall,
        "group_states": {g.id: s for g, s in zip(support.groups, states)},
        "satisfied_groups": satisfied_groups,
    }


def minimal_groups(support: ClaimSupport,
                   entails: set[tuple[str, str]]) -> list[str]:
    """Ids of satisfied groups with no redundant member (MEG check).

    Redundancy is group-relative: a member is redundant only when the
    group without it still covers a satisfied group of the same claim.
    Flat entailment pairs cannot decide this, because a pair licensed
    inside one group says nothing about its role in another.
    """
    satisfied = [g for g in support.groups
                 if group_status(g, entails) == "satisfied"]
    minimal = []
    for group in satisfied:
        redundant = False
        for member in group.members:
            rest = frozenset(m for m in group.members if m != member)
            if any(set(other.members) <= set(rest)
                   for other in satisfied if other.id != group.id):
                redundant = True
                break
        if not redundant:
            minimal.append(group.id)
    return minimal
