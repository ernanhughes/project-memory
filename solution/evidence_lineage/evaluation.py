"""Chapter 2 instrument extensions earned by Chapter 7.

Each scorer is deterministic over fixture ledger truth. LLM/NLI
judges are not used in v0.1: AttributionBench and CiteEval show
automatic support judgements are unreliable, so the suite measures
the layer against controlled ground truth first.

No single "provenance score" is produced; dimensions stay separate.
"""

from __future__ import annotations


def precision_recall_f1(predicted: set, expected: set) -> dict:
    tp = len(predicted & expected)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    precision = tp / (tp + fp) if (tp + fp) else 1.0 if not expected else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn}


def support_scores(predicted_edges: set[tuple[str, str]],
                   true_edges: set[tuple[str, str]]) -> dict:
    """Support precision / coverage over (claim, evidence) pairs."""
    out = precision_recall_f1(predicted_edges, true_edges)
    return {"support_precision": out["precision"],
            "support_coverage": out["recall"],
            "support_f1": out["f1"], **out}


def provenance_precision(cited: set[tuple[str, str]],
                         true_support: set[tuple[str, str]],
                         topical_only: set[tuple[str, str]]) -> dict:
    """Penalise genuine-but-non-supporting citations.

    ``topical_only`` holds retrieved, topically relevant pairs that do
    not license the claim (losing-side passages, wrong-hop
    benchmarks, associative neighbours).
    """
    borrowed = cited & topical_only
    valid = cited & true_support
    precision = (len(valid) / len(cited)) if cited else 1.0
    return {"provenance_precision": precision,
            "borrowed_authority_citations": sorted(
                f"{c}->{e}" for c, e in borrowed),
            "borrowed_count": len(borrowed)}


def lineage_completeness(traces: dict[str, dict]) -> dict:
    """Share of claims whose trace grounds in raw spans with no open end."""
    complete = sum(1 for t in traces.values()
                   if t["raw_grounded"] and not t["open_lineages"])
    total = len(traces)
    return {"lineage_completeness": (complete / total) if total else 1.0,
            "raw_grounding_rate": sum(1 for t in traces.values()
                                      if t["raw_grounded"]) / total
            if total else 1.0,
            "complete": complete, "total": total}


def group_validity(predicted_groups: dict[str, list[frozenset]],
                   true_groups: dict[str, list[frozenset]]) -> dict:
    """Minimal-evidence-group correctness per claim (exact + soft)."""
    exact_hits = 0
    soft_scores: list[float] = []
    for claim_id, true_sets in true_groups.items():
        pred_sets = predicted_groups.get(claim_id, [])
        if not true_sets and not pred_sets:
            # Correctly predicting that no support exists is exact.
            exact_hits += 1
            soft_scores.append(1.0)
            continue
        if any(p in true_sets for p in pred_sets):
            exact_hits += 1
        best = 0.0
        for pred in pred_sets:
            for true in true_sets:
                inter = len(pred & true)
                union = len(pred | true)
                score = inter / union if union else 1.0
                best = max(best, score)
        soft_scores.append(best)
    total = len(true_groups)
    return {
        "group_exact_match_rate": (exact_hits / total) if total else 1.0,
        "group_soft_match_mean": (sum(soft_scores) / len(soft_scores)
                                  if soft_scores else 1.0),
    }


def echo_scores(predicted_echo: set[str], true_echo: set[str],
                predicted_independent: set[str],
                true_independent: set[str]) -> dict:
    """Echo vs corroboration: repetition must not count as evidence."""
    echo = precision_recall_f1(predicted_echo, true_echo)
    # Echo inflation rate: echoes presented as independent evidence.
    inflated = predicted_independent & true_echo
    return {"echo_precision": echo["precision"],
            "echo_recall": echo["recall"],
            "echo_inflation_count": len(inflated),
            "echo_inflation_rate": (len(inflated) / len(predicted_independent)
                                    if predicted_independent else 0.0)}


def error_localisation(predicted_stage: dict[str, str | None],
                       true_stage: dict[str, str | None]) -> dict:
    hits = sum(1 for c, s in true_stage.items()
               if predicted_stage.get(c) == s)
    total = len(true_stage)
    return {"error_localisation_accuracy": (hits / total) if total else 1.0,
            "hits": hits, "total": total}


def impact_scores(predicted: set[str], expected: set[str]) -> dict:
    out = precision_recall_f1(predicted, expected)
    return {"impact_recall": out["recall"],
            "impact_precision": out["precision"], **out}


def answer_evidence_divergence(cases: list[dict]) -> dict:
    """Answer correctness and evidence correctness stay separate.

    Each case: {answer_correct: bool, evidence_correct: bool}.
    """
    cells = {"correct_answer_correct_evidence": 0,
             "correct_answer_wrong_evidence": 0,
             "wrong_answer_correct_evidence": 0,
             "wrong_answer_wrong_evidence": 0}
    for case in cases:
        key = (f"{'correct' if case['answer_correct'] else 'wrong'}_answer_"
               f"{'correct' if case['evidence_correct'] else 'wrong'}_evidence")
        cells[key] += 1
    return cells
