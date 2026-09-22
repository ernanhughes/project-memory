"""Revision infrastructure: dependency impact and retraction.

Chapter 7 answers which claims are affected when evidence changes.
It never decides what the new belief should be — that is Chapter 8.

Withdrawing evidence never deletes history: the evidence node stays
with a withdrawn/invalidated mark, and dependents are flagged
``REQUIRES_REEVALUATION``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .evidence import ClaimSupport, claim_support_status
from .lineage import LineageGraph


@dataclass
class ImpactReport:
    evidence_id: str
    affected_claims: list[str] = field(default_factory=list)
    still_supported: list[str] = field(default_factory=list)
    status_after: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "affected_claims": self.affected_claims,
            "still_supported": self.still_supported,
            "status_after": self.status_after,
        }


def impact_of(graph: LineageGraph,
              supports: dict[str, ClaimSupport],
              entails: set[tuple[str, str]],
              evidence_id: str) -> ImpactReport:
    """Which downstream claims depend on this evidence, and what
    happens to each if it is withdrawn (one support leg removed)."""
    report = ImpactReport(evidence_id=evidence_id)
    for claim_id in graph.dependents_of(evidence_id):
        support = supports.get(claim_id)
        if support is None:
            continue
        before = claim_support_status(support, entails)["status"]
        remaining = {(c, e) for (c, e) in entails if e != evidence_id}
        after = claim_support_status(support, remaining)["status"]
        report.status_after[claim_id] = after
        if after == "FULLY_SUPPORTED":
            report.still_supported.append(claim_id)
        elif before in ("FULLY_SUPPORTED", "PARTIALLY_SUPPORTED"):
            # Only claims that actually lose license require
            # reevaluation. A claim that was already unsupported
            # (e.g. derivation-only dependents) loses nothing.
            report.affected_claims.append(claim_id)
    report.affected_claims.sort()
    report.still_supported.sort()
    return report


def retract_evidence(graph: LineageGraph,
                     supports: dict[str, ClaimSupport],
                     entails: set[tuple[str, str]],
                     evidence_id: str) -> dict:
    """Keystone retraction experiment step: remove one leg, recompute.

    Returns the impact report plus the before/after verdict table.
    History is preserved: nothing is deleted from the graph.
    """
    before = {cid: claim_support_status(s, entails)["status"]
              for cid, s in supports.items()}
    report = impact_of(graph, supports, entails, evidence_id)
    after = dict(before)
    after.update(report.status_after)
    return {
        "evidence_id": evidence_id,
        "before": before,
        "after": after,
        "impact": report.to_dict(),
        "requires_reevaluation": report.affected_claims,
    }
