"""Context metrics, measured before any answer is generated.

A strong reader can hide a bad bundle, so context quality is scored
first and separately, against the hidden ledger in ``fixtures.py``:

``must_include_recall``      required evidence admitted / required
``useful_recall``            required or helpful admitted / all such
``context_precision``        required or helpful admitted / all admitted
``distractor_admission``     in-scope but unhelpful admitted / admitted
``harmful_admission``        superseded or misleading admitted / admitted
``cross_project_leakage``    out-of-project admitted / admitted
``redundancy_rate``          restatements admitted alongside their source
``provenance_completeness``  bundle items carrying at least one source ref
``bundle_tokens``            cost, at a fixed budget

Every number is reported per task before any aggregate, per the
Chapter 2 instrument.
"""

from __future__ import annotations

from .corpus import by_id
from .fixtures import DISTRACTOR, HARMFUL, MUST, OPTIONAL, SHOULD, Task
from .model import ContextBundle, ContextTrace, ProjectFrame


def _safe(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def score_bundle(task: Task, bundle: ContextBundle, trace: ContextTrace,
                 frame: ProjectFrame) -> dict:
    units = by_id()
    admitted = bundle.unit_ids()
    admitted_set = set(admitted)
    labels = [task.label(u) for u in admitted]
    required = task.required()
    useful = task.useful()

    echo_dupes = sum(
        1 for u in admitted
        if units[u].echo_of is not None and units[u].echo_of in admitted_set)
    out_of_scope = sum(1 for u in admitted
                       if units[u].project_id not in frame.scope())
    sourced = sum(1 for item in bundle.items if item.source_refs)

    return {
        "condition": bundle.condition,
        "must_include_recall": _safe(
            len(admitted_set & required), len(required)),
        "useful_recall": _safe(len(admitted_set & useful), len(useful)),
        "context_precision": _safe(
            sum(1 for lab in labels if lab in (MUST, SHOULD)), len(admitted)),
        "distractor_admission": _safe(
            sum(1 for lab in labels if lab == DISTRACTOR), len(admitted)),
        "harmful_admission": _safe(
            sum(1 for lab in labels if lab == HARMFUL), len(admitted)),
        "optional_admission": _safe(
            sum(1 for lab in labels if lab == OPTIONAL), len(admitted)),
        "cross_project_leakage": _safe(out_of_scope, len(admitted)),
        "redundancy_rate": _safe(echo_dupes, len(admitted)),
        "provenance_completeness": _safe(sourced, len(bundle.items)),
        "admitted_units": len(admitted),
        "bundle_items": len(bundle.items),
        "bundle_tokens": bundle.tokens,
        "budget_tokens": bundle.budget_tokens,
        "candidate_count": len(trace.candidates),
        "latency_ms": round(trace.latency_ms, 2),
    }


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return round(len(sa & sb) / len(sa | sb), 4)


def bundle_divergence(left: ContextBundle, right: ContextBundle) -> dict:
    """How much two bundles differ. Used by the same-query fixtures."""
    return {
        "jaccard": jaccard(left.unit_ids(), right.unit_ids()),
        "only_left": sorted(set(left.unit_ids()) - set(right.unit_ids())),
        "only_right": sorted(set(right.unit_ids()) - set(left.unit_ids())),
        "shared": sorted(set(left.unit_ids()) & set(right.unit_ids())),
    }


# --------------------------------------------------------------------------
# Answer scoring: mechanical, against the task's declared claims.
# --------------------------------------------------------------------------

def score_answer(task: Task, answer: str) -> dict:
    import re
    text = answer.lower()
    covered = []
    for name, alternatives in task.key_claims:
        hit = any(re.search(alt, text) for alt in alternatives)
        covered.append((name, hit))
    violations = []
    for name, patterns in task.forbidden_claims:
        hit = any(re.search(pat, text) for pat in patterns)
        violations.append((name, hit))
    return {
        "key_claim_coverage": _safe(sum(1 for _, hit in covered if hit),
                                    len(covered)) if covered else None,
        "key_claims": {name: hit for name, hit in covered},
        "forbidden_claim_rate": _safe(
            sum(1 for _, hit in violations if hit),
            len(violations)) if violations else 0.0,
        "forbidden_claims": {name: hit for name, hit in violations},
        "answer_chars": len(answer),
    }


# --------------------------------------------------------------------------
# Failure attribution: where a wrong answer was actually lost.
# --------------------------------------------------------------------------

E_CODES = {
    "E0": "required evidence absent from the corpus",
    "E1": "present but never retrieved as a candidate",
    "E2": "retrieved but ruled ineligible by the frame",
    "E3": "eligible but outranked and lost to the budget",
    "E4": "admitted alongside superseded or harmful evidence",
    "E5": "coalescing folded away a needed distinction",
    "E6": "context sufficient; the reader failed",
}


def attribute_failure(task: Task, bundle: ContextBundle, trace: ContextTrace,
                      answer_score: dict | None = None) -> dict:
    """Classify each missing requirement, and the run as a whole."""
    units = by_id()
    admitted = set(bundle.unit_ids())
    per_unit: dict[str, str] = {}
    for unit_id in sorted(task.required() - admitted):
        if unit_id not in units:
            per_unit[unit_id] = "E0"
            continue
        candidate = next((c for c in trace.candidates
                          if c.unit_id == unit_id), None)
        if candidate is None:
            per_unit[unit_id] = "E1"
        elif not candidate.eligible:
            per_unit[unit_id] = "E2"
        elif candidate.coalesced_into is not None:
            per_unit[unit_id] = "E5"
        else:
            per_unit[unit_id] = "E3"
    harmful_admitted = sorted(task.harmful() & admitted)
    codes = sorted(set(per_unit.values()))
    if harmful_admitted:
        codes.append("E4")
    if (not codes and answer_score is not None
            and answer_score.get("key_claim_coverage") is not None
            and answer_score["key_claim_coverage"] < 1.0):
        codes.append("E6")
    return {"per_unit": per_unit, "harmful_admitted": harmful_admitted,
            "codes": sorted(set(codes)),
            "legend": {c: E_CODES[c] for c in sorted(set(codes))}}
