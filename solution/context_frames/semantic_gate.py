"""Semantic gate v2: establishment hints -> class -> policy action.

The gate consumes establishment hints derived from ledger reconciliation
evidence (frame_evidence.py) and maps them to the already-earned policy
actions. Classes ARE the hint vocabulary; no class is added unless a
fixture forces it (none has):

    corroborated -> HARD_FRAME
    weak         -> SOFT_FRAME
    stale        -> QUERY_ONLY_FALLBACK
    conflicting  -> QUERY_ONLY_FALLBACK
    unknown      -> QUERY_ONLY_FALLBACK,
                    except abstention_acceptable -> ABSTAIN,
                    except consequential+needs_memory -> REQUEST_MORE_EVIDENCE

BROADEN_RETRIEVAL stays unmapped: the v1 backtest rejected
conflicting->broaden on nil evidence, and no dev fixture forces it
(see the tuning record). No scalar confidence anywhere: every branch
is a deterministic function of hint + scenario metadata, and reason
codes arise from the control flow taken, never post-hoc prose.

Hint precedence when several records mention the subject (rare by
fixture design, deterministic regardless): conflicting vetoes first,
then stale, then corroborated over weak, with unknown only when
nothing else speaks. Safety vetoes before strength.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import frame_safety as fs
from . import frame_evidence as fe

SEMANTIC_GATE_VERSION = "semantic-gate-v1"

# Re-export the earned action set so callers need only this module.
HARD_FRAME = fs.HARD_FRAME
SOFT_FRAME = fs.SOFT_FRAME
QUERY_ONLY = fs.QUERY_ONLY
BROADEN = fs.BROADEN
REQUEST_MORE = fs.REQUEST_MORE
ABSTAIN = fs.ABSTAIN

# Safety-first precedence over coexisting hints.
_PRECEDENCE = ("conflicting", "stale", "corroborated", "weak", "unknown")


@dataclass(frozen=True)
class GateDecision:
    establishment: str  # one of the hint classes
    action: str
    hint_basis: tuple
    reason: str


def decide(hints: list[dict], needs_memory: bool, consequential: bool,
           abstention_acceptable: bool) -> GateDecision:
    """Map establishment hints + scenario metadata to a policy action."""
    by_hint = {}
    for h in hints:
        by_hint.setdefault(h["hint"], h)
    establishment = next(
        (h for h in _PRECEDENCE if h in by_hint), "unknown")
    basis = tuple(by_hint[establishment]["basis"]) if establishment in by_hint else ()
    authority = (by_hint[establishment]["authority"]
                 if establishment in by_hint else "none")
    if establishment == "corroborated":
        return GateDecision(
            establishment, HARD_FRAME, basis,
            f"hint=corroborated:{authority}; hard framing licensed")
    if establishment == "weak":
        return GateDecision(
            establishment, SOFT_FRAME, basis,
            f"hint=weak:{authority}; frame reranks, cannot exclude")
    if establishment in ("stale", "conflicting"):
        return GateDecision(
            establishment, QUERY_ONLY, basis,
            f"hint={establishment}; frame untrusted, query-only fallback")
    # unknown: abstention first (acceptable), then request (consequential
    # work that needs memory), else fall back.
    if abstention_acceptable:
        return GateDecision(
            establishment, ABSTAIN, basis,
            "hint=unknown+abstention-acceptable; decline to act")
    if consequential and needs_memory:
        return GateDecision(
            establishment, REQUEST_MORE, basis,
            "hint=unknown+consequential; request more evidence")
    return GateDecision(
        establishment, QUERY_ONLY, basis,
        "hint=unknown; query-only fallback")


def decide_for_subject(graph, rset, subject: str, as_of: str,
                       needs_memory: bool, consequential: bool,
                       abstention_acceptable: bool,
                       later=()) -> GateDecision:
    """End-to-end: ledger evidence -> hints -> decision. The composition
    the runner uses; unit-tested here so the runner stays thin.

    Correspondence-only evidence is routed explicitly: topical records
    that establish nothing license fallback action (QUERY_ONLY), never
    refusal and never hard framing. Bare absence of evidence takes the
    unknown branch instead (abstain / request / fall back). The
    distinction is presence of topical evidence, not outcome counts.
    """
    hints = fe.establishment_hints_for(graph, rset, subject, as_of,
                                       later=later)
    if not hints and _has_correspondence(rset, subject):
        return GateDecision(
            "unknown", QUERY_ONLY, (),
            "correspondence-only evidence: topical but unestablished; "
            "fall back and act")
    return decide(hints, needs_memory, consequential, abstention_acceptable)


def _has_correspondence(rset, subject: str) -> bool:
    from evidence_lineage import reconciliation as R
    for rec in rset.records.values():
        if (subject in (rec.subject_a, rec.subject_b)
                and rec.relationship == R.Relationship.CORRESPONDENCE):
            return True
    return False
