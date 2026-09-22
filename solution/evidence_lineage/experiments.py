"""E7 experiment suite: deterministic, ledger-scored, offline.

Baselines (evidence representations of increasing structure):

* P0 source-pointer: one pointer per claim (the ADR rationale span).
* P1 direct citation: claim linked to every retrieved candidate,
  including echoes and topical distractors.
* P2 support edges: explicit SUPPORTED_BY edges with support groups.
* P3 full lineage: P2 plus derivation/echo edges, reverse
  verification and impact analysis.

No LLM calls anywhere in v0.1; the manifest records zero model
dependency so a future LLM-backed condition is a new run, not a
silent substitution.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from . import claims as claim_mod
from .config import EvidenceConfig
from . import evaluation as ev
from . import fixtures as fx
from .evidence import claim_support_status
from .revision import impact_of, retract_evidence
from .verification import verify_backward

SUITE_VERSION = "e7-suite-v0.1"


def _predicted_pointer_edges() -> set[tuple[str, str]]:
    # P0: every claim points at the ADR rationale alone.
    return {(c, "a07-rationale") for c, _ in fx.CLAIMS}


def _predicted_direct_edges() -> set[tuple[str, str]]:
    # P1: everything retrieved is cited, echoes included.
    edges = set(fx.ENTAILS)
    edges |= fx.TOPICAL_ONLY
    return edges


def exp_e7a_pointer_vs_support() -> dict:
    """E7-A: pointer vs support graph on simple and multi-source cases."""
    simple = {"claim-atomic", "claim-contention", "claim-narrow"}
    multi = {"claim-main"}
    trap = {"claim-budget", "claim-perf", "claim-causal-gap"}
    results = {}
    for name, level in (("P0_pointer", _predicted_pointer_edges()),
                        ("P1_direct", _predicted_direct_edges()),
                        ("P2_support", set(fx.ENTAILS))):
        per_case = {}
        for claim in simple | multi | trap:
            pred = {(c, e) for (c, e) in level if c == claim}
            true = {(c, e) for (c, e) in fx.ENTAILS if c == claim}
            per_case[claim] = ev.support_scores(pred, true)
        all_pred = {(c, e) for (c, e) in level
                    if c in simple | multi | trap}
        all_true = {(c, e) for (c, e) in fx.ENTAILS
                    if c in simple | multi | trap}
        results[name] = {
            "overall": ev.support_scores(all_pred, all_true),
            "simple_mean_coverage": sum(
                per_case[c]["support_coverage"] for c in simple
            ) / len(simple),
            "multi_coverage": per_case["claim-main"]["support_coverage"],
            "trap_precision": sum(
                per_case[c]["support_precision"] for c in trap
            ) / len(trap),
            "per_case": per_case,
        }
    return {"question": "single pointer vs explicit support relation",
            "results": results}


def exp_e7b_claim_extraction() -> dict:
    """E7-B: C0 vs C1 vs C2 on labelled tricky sentences."""
    out = {}
    for name, fn in (("C0", claim_mod.extract_claims_c0),
                     ("C1", claim_mod.extract_claims_c1),
                     ("C2", claim_mod.extract_claims_c2)):
        total_expected = 0
        total_matched = 0
        invented = 0
        missed_qualifier = 0
        per_case = []
        for case in fx.EXTRACTION_CASES:
            got = [c.text for c in fn(case["sentence"], artifact="t")
                   if not c.abstained]
            expected = case["expected"]
            total_expected += len(expected)
            matched = 0
            for exp in expected:
                if any(exp.rstrip(".").lower() in g.rstrip(".").lower()
                       or g.rstrip(".").lower() in exp.rstrip(".").lower()
                       for g in got):
                    matched += 1
            total_matched += matched
            extra = len(got) - matched
            if extra > 0:
                invented += extra
            if case.get("negated") and got:
                live = [c for c in fn(case["sentence"], artifact="t")
                        if not c.abstained]
                if not any(c.negated for c in live):
                    missed_qualifier += 1
            if case.get("conditional") and got:
                live = [c for c in fn(case["sentence"], artifact="t")
                        if not c.abstained]
                if not any(c.conditional for c in live):
                    missed_qualifier += 1
            if case.get("attributed") and got:
                live = [c for c in fn(case["sentence"], artifact="t")
                        if not c.abstained]
                if not any(c.attributed for c in live):
                    missed_qualifier += 1
            per_case.append({"sentence": case["sentence"][:48],
                             "got": len(got),
                             "expected": len(expected),
                             "matched": matched})
        coverage = (total_matched / total_expected) if total_expected else 1.0
        out[name] = {"coverage": coverage,
                     "matched": total_matched,
                     "expected": total_expected,
                     "invented_extra": invented,
                     "missed_qualifiers": missed_qualifier,
                     "per_case": per_case,
                     "report": claim_mod.extraction_report(
                         fn("PostgreSQL was selected because SQLite "
                            "contention caused the importer failures. "
                            "They fixed it next quarter.",
                            artifact="demo"))}
    return {"question": "claim extraction omissions, inventions, flags",
            "results": out}


def exp_e7c_multi_source() -> dict:
    """E7-C: single-source, conjunctive and alternative groups."""
    supports = fx.build_supports()
    statuses = {cid: claim_support_status(s, fx.ENTAILS)
                for cid, s in supports.items()}
    true_frozen = {cid: [frozenset(g) for g in groups]
                   for cid, groups in fx.SUPPORT_GROUPS.items()}
    # Predicted groupings per baseline representation.
    pointer = _predicted_pointer_edges()
    direct = _predicted_direct_edges()
    pred_p0 = {cid: [frozenset({e}) for (c, e) in pointer if c == cid]
               for cid, _ in fx.CLAIMS}
    retrieved: dict[str, set[str]] = {}
    for (c, e) in direct:
        retrieved.setdefault(c, set()).add(e)
    pred_p1 = {cid: [frozenset(retrieved.get(cid, set()))]
               if retrieved.get(cid) else []
               for cid, _ in fx.CLAIMS}
    pred_p2 = {}
    for cid, sup in supports.items():
        groups = []
        for gid in statuses[cid]["satisfied_groups"]:
            group = sup.group(gid)
            groups.append(frozenset(group.members))
        pred_p2[cid] = groups
    validity = {name: ev.group_validity(pred, true_frozen)
                for name, pred in (("P0_pointer", pred_p0),
                                   ("P1_direct", pred_p1),
                                   ("P2_support", pred_p2))}
    return {"question": "support-group correctness incl. alternatives",
            "statuses": {c: s["status"] for c, s in statuses.items()},
            "satisfied_groups_claim_main": statuses["claim-main"][
                "satisfied_groups"],
            "group_validity": validity}


def exp_e7d_echo() -> dict:
    """E7-D: paraphrase-graded echo detection."""
    src_text = [t for sid, _, t in fx.SPANS if sid == "a07-decision"][0]
    truth_echo = {c["id"] for c in fx.ECHO_LADDER}
    thresholds = (0.3, 0.55, 0.8)
    rows = []
    for threshold in thresholds:
        detected = {c["id"] for c in fx.ECHO_LADDER
                    if fx.echo_detector(c["text"], src_text, threshold)}
        scores = ev.echo_scores(detected, truth_echo, set(), set())
        rows.append({"threshold": threshold,
                     "detected": sorted(detected),
                     "recall": scores["echo_recall"]})
    per_rung = []
    for case in fx.ECHO_LADDER:
        overlap = fx.token_overlap(case["text"], src_text)
        per_rung.append({"id": case["id"], "overlap": round(overlap, 3),
                         "detected_at_0.55": overlap >= 0.55})
    return {"question": "repetition identified as derivation, not evidence",
            "threshold_sweep": rows, "per_rung": per_rung,
            "note": "overlap heuristic handles near-duplicates; heavy "
                    "paraphrase needs recorded derivation edges"}


def exp_e7e_connectivity_gap() -> dict:
    """E7-E: graph-connected distractors must fail the support test."""
    # Candidates a Chapter 4/5 layer could plausibly retrieve.
    candidates = {
        "claim-main": {"s19-benchmark", "i21-incident", "a07-rationale",
                       "s17-sqlite-case", "s40-other-importer",
                       "w10-summary", "r06-echo"},
        "claim-budget": {"inv183-span"},
    }
    filtered = {}
    for claim, cands in candidates.items():
        kept = {e for e in cands if (claim, e) in fx.ENTAILS}
        rejected = sorted(cands - kept)
        truth_reject = sorted(e for e in cands
                              if (claim, e) not in fx.ENTAILS)
        filtered[claim] = {
            "kept": sorted(kept),
            "rejected": rejected,
            "rejection_recall": (len([e for e in rejected
                                      if e in truth_reject])
                                 / len(truth_reject) if truth_reject else 1.0),
        }
    return {"question": "connected does not imply supporting",
            "results": filtered}


def exp_e7f_lineage(graph=None) -> dict:
    """E7-F: multi-stage lineage completeness and raw grounding."""
    graph = graph or fx.build_graph()
    traces = {cid: graph.trace_to_sources(cid)
              for cid, _ in fx.CLAIMS}
    completeness = ev.lineage_completeness(traces)
    hallucinated = traces["claim-14pct"]
    return {"question": "claim to raw evidence through every stage",
            "completeness": completeness,
            "claim_14pct_trail": hallucinated["trail"],
            "claim_14pct_grounded": hallucinated["grounded_spans"],
            "claim_main_grounded": traces["claim-main"]["grounded_spans"]}


def exp_e7g_localisation() -> dict:
    """E7-G: injected unsupported stages vs localised stages."""
    predicted, truth = {}, {}
    details = {}
    for claim_id, stage_truth in fx.STAGE_SUPPORT.items():
        verification = verify_backward(claim_id, dict(stage_truth))
        predicted[claim_id] = verification.error_stage
        truth[claim_id] = fx.ERROR_STAGE_TRUTH[claim_id]
        details[claim_id] = verification.to_dict()
    return {"question": "where did unsupported content first appear",
            "scores": ev.error_localisation(predicted, truth),
            "predicted": predicted, "truth": truth, "details": details}


def exp_e7h_keystone(graph=None) -> dict:
    """E7-H: remove a necessary leg; mark affected claims."""
    graph = graph or fx.build_graph()
    supports = fx.build_supports()
    narrow = retract_evidence(graph, supports, fx.ENTAILS, "s19-benchmark")
    rationale = retract_evidence(graph, supports, fx.ENTAILS,
                                 "a07-rationale")
    # Fixture truth for s19 removal: claim-narrow affected; claim-main
    # survives via the replicate group.
    expected_narrow = {"claim-narrow"}
    got_narrow = set(narrow["requires_reevaluation"])
    expected_rat = {"claim-main", "claim-atomic"}
    got_rat = set(rationale["requires_reevaluation"])
    return {"question": "keystone retraction marks dependents",
            "retract_s19": narrow,
            "retract_a07": rationale,
            "s19_impact": ev.impact_scores(got_narrow, expected_narrow),
            "a07_impact": ev.impact_scores(got_rat, expected_rat)}


def exp_e7i_redundant(graph=None) -> dict:
    """E7-I: remove one redundant group; claim stays supported."""
    graph = graph or fx.build_graph()
    supports = fx.build_supports()
    report = retract_evidence(graph, supports, fx.ENTAILS, "s44-replicate")
    return {"question": "redundant evidence removal keeps support",
            "report": report,
            "claim_main_after": report["after"]["claim-main"]}


def exp_e7j_divergence() -> dict:
    """E7-J: answer and evidence scores must be able to diverge."""
    cells = ev.answer_evidence_divergence(fx.DIVERGENCE_CASES)
    return {"question": "right answer with wrong chain fails justification",
            "cells": cells,
            "justification_failures": cells[
                "correct_answer_wrong_evidence"]}


def run_suite(config: EvidenceConfig | None = None) -> dict:
    """Run E7-A..E7-J and freeze the manifest."""
    config = config or EvidenceConfig()
    started = time.perf_counter()
    graph = fx.build_graph()
    experiments = {
        "E7-A": exp_e7a_pointer_vs_support(),
        "E7-B": exp_e7b_claim_extraction(),
        "E7-C": exp_e7c_multi_source(),
        "E7-D": exp_e7d_echo(),
        "E7-E": exp_e7e_connectivity_gap(),
        "E7-F": exp_e7f_lineage(graph),
        "E7-G": exp_e7g_localisation(),
        "E7-H": exp_e7h_keystone(graph),
        "E7-I": exp_e7i_redundant(graph),
        "E7-J": exp_e7j_divergence(),
    }
    elapsed_ms = (time.perf_counter() - started) * 1000
    # Cost accounting: deterministic offline run.
    costs = {"llm_calls": 0, "tokens": 0,
             "latency_ms": round(elapsed_ms, 1),
             "graph_nodes": len(graph.nodes),
             "graph_edges": len(graph.edges)}
    for name, experiment in experiments.items():
        experiment["question_id"] = name
    return {
        "suite": SUITE_VERSION,
        "config": config.to_dict(),
        "frozen_at": datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"),
        "model_dependency": "none (ledger-deterministic-v0.1)",
        "experiments": experiments,
        "costs": costs,
        "health": graph.health(),
    }
