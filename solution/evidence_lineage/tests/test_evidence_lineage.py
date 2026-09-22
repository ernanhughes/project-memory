"""Tests for the evidence-lineage layer (Chapter 7)."""

import pytest

from evidence_lineage import claims as claim_mod
from evidence_lineage import fixtures as fx
from evidence_lineage.evidence import (claim_support_status, group_status,
                                       minimal_groups)
from evidence_lineage.evaluation import (answer_evidence_divergence,
                                         echo_scores, error_localisation,
                                         group_validity, impact_scores,
                                         lineage_completeness,
                                         provenance_precision,
                                         support_scores)
from evidence_lineage.experiments import run_suite
from evidence_lineage.lineage import Edge, EdgeKind, LineageGraph, Node
from evidence_lineage.lineage import NodeKind
from evidence_lineage.revision import impact_of, retract_evidence
from evidence_lineage.verification import verify_backward


@pytest.fixture()
def graph():
    return fx.build_graph()


@pytest.fixture()
def supports():
    return fx.build_supports()


# -- claims ----------------------------------------------------------

def test_c0_single_sentence():
    found = claim_mod.extract_claims_c0("PostgreSQL was selected.")
    assert len(found) == 1 and found[0].text == "PostgreSQL was selected."


def test_c1_splits_conjunction():
    found = [c for c in claim_mod.extract_claims_c1(
        "PostgreSQL was selected and the importer recovered and "
        "operational costs rose.") if not c.abstained]
    assert len(found) >= 3
    causal = [c for c in claim_mod.extract_claims_c1(
        "PostgreSQL was selected because SQLite contention caused the "
        "importer failures.") if not c.abstained]
    assert len(causal) >= 2


def test_c1_flags_negation_and_conditional():
    neg = [c for c in claim_mod.extract_claims_c1(
        "The importer never failed under SQLite.") if not c.abstained]
    assert any(c.negated for c in neg)
    cond = [c for c in claim_mod.extract_claims_c1(
        "If contention returns, we will revisit the decision.")
        if not c.abstained]
    assert any(c.conditional for c in cond)


def test_c1_flags_attribution():
    found = [c for c in claim_mod.extract_claims_c1(
        "The operator reported that the importer timed out.")
        if not c.abstained]
    assert any(c.attributed for c in found)


def test_c2_abstains_on_unresolvable_reference():
    found = claim_mod.extract_claims_c2("They fixed it next quarter.")
    assert found and all(c.abstained for c in found)


def test_c2_drops_non_verifiable():
    found = claim_mod.extract_claims_c2("Is that true?")
    assert all(c.abstained for c in found)


def test_malformed_extractor_input():
    assert claim_mod.extract_claims_c0("") == []
    assert claim_mod.extract_claims_c1("  ") == []


# -- evidence --------------------------------------------------------

def test_direct_support():
    supports = fx.build_supports()
    status = claim_support_status(supports["claim-atomic"], fx.ENTAILS)
    assert status["status"] == "FULLY_SUPPORTED"


def test_non_supporting_topical_evidence_rejected():
    supports = fx.build_supports()
    status = claim_support_status(supports["claim-main"], fx.ENTAILS)
    # Topical-only pairs are not in ENTAILS, so they add no support.
    assert ("claim-main", "s17-sqlite-case") not in fx.ENTAILS
    assert status["status"] == "FULLY_SUPPORTED"


def test_partial_support():
    from evidence_lineage.evidence import ClaimSupport, SupportGroup
    support = ClaimSupport("x", groups=[
        SupportGroup("x-g0", "x", ("s19-benchmark", "i21-incident"))])
    partial = {("x", "s19-benchmark")}
    assert group_status(support.groups[0], partial) == "partial"


def test_conjunctive_group_needs_all_members():
    supports = fx.build_supports()
    without_incident = {(c, e) for (c, e) in fx.ENTAILS
                        if e != "i21-incident"}
    status = claim_support_status(supports["claim-main"], without_incident)
    assert status["status"] != "FULLY_SUPPORTED"


def test_alternative_group_keeps_support():
    supports = fx.build_supports()
    without_s19 = {(c, e) for (c, e) in fx.ENTAILS
                   if e != "s19-benchmark"}
    status = claim_support_status(supports["claim-main"], without_s19)
    assert status["status"] == "FULLY_SUPPORTED"
    assert status["satisfied_groups"] == ["claim-main-g1"]


def test_minimal_groups():
    supports = fx.build_supports()
    assert (sorted(minimal_groups(supports["claim-main"], fx.ENTAILS))
            == ["claim-main-g0", "claim-main-g1"])


# -- derivation / echo -----------------------------------------------

def test_no_derived_as_support(graph):
    # DERIVED_FROM edges exist but support_for returns only SUPPORTED_BY.
    assert graph.lineage_of("comm-17")
    assert graph.support_for("claim-main")
    derived_targets = {e.target for e in graph.lineage_of("comm-17")}
    support_targets = {e.target for e in graph.support_for("claim-main")}
    assert "comm-17" not in support_targets
    _ = derived_targets


def test_paraphrase_echo_overlap_degrades():
    src = [t for sid, _, t in fx.SPANS if sid == "a07-decision"][0]
    overlaps = [fx.token_overlap(c["text"], src) for c in fx.ECHO_LADDER]
    assert overlaps[0] > overlaps[-1]  # exact > changed terminology


def test_echo_chain_resolves():
    graph = fx.build_graph()
    assert graph._resolve_echo("r06-echo") == "a07-decision"


# -- lineage ----------------------------------------------------------

def test_source_to_answer_trace(graph):
    trace = graph.trace_to_sources("claim-main")
    assert trace["raw_grounded"]
    assert "s19-benchmark" in trace["grounded_spans"]


def test_missing_intermediate_gives_open_lineage(graph):
    graph.add_node(Node("lonely", NodeKind.CLAIM, "unsupported"))
    trace = graph.trace_to_sources("lonely")
    assert not trace["raw_grounded"]
    assert trace["open_lineages"] == ["lonely"]


def test_cycle_rejected(graph):
    with pytest.raises(ValueError):
        graph.add_edge(Edge("s14-contention", "comm-17",
                            EdgeKind.DERIVED_FROM))


def test_raw_grounding_check(graph):
    trace = graph.trace_to_sources("claim-redis")
    # Harmful derived relation has no path to any raw span.
    assert not trace["raw_grounded"]


# -- error localisation -----------------------------------------------

def test_known_failure_stage():
    verification = verify_backward(
        "claim-14pct", dict(fx.STAGE_SUPPORT["claim-14pct"]))
    assert verification.final_verdict == "NOT_FULLY_SUPPORTED"
    assert verification.error_stage == "summary"


def test_downstream_propagation_marks_reader():
    verification = verify_backward(
        "claim-14pct", dict(fx.STAGE_SUPPORT["claim-14pct"]))
    reader = next(s for s in verification.stages if s.stage == "reader")
    assert reader.supported_by_inputs is False


# -- retraction ---------------------------------------------------------

def test_keystone_removal(supports, graph):
    report = retract_evidence(graph, supports, fx.ENTAILS, "s19-benchmark")
    assert "claim-narrow" in report["requires_reevaluation"]
    # claim-main survives via the replicate group.
    assert "claim-main" not in report["requires_reevaluation"]


def test_redundant_removal_keeps_support(supports, graph):
    report = retract_evidence(graph, supports, fx.ENTAILS, "s44-replicate")
    assert report["after"]["claim-main"] == "FULLY_SUPPORTED"


def test_impact_set(graph, supports):
    report = impact_of(graph, supports, fx.ENTAILS, "a07-rationale")
    assert set(report.affected_claims) == {"claim-atomic", "claim-main"}


# -- integration --------------------------------------------------------

def test_ch3_source_present(graph):
    assert "s19-benchmark" in graph.nodes


def test_ch4_graph_object_present(graph):
    assert "ext-rel-1" in graph.nodes


def test_ch5_trace_preserved_not_support(graph):
    assert graph.retrieval_traces["claim-budget"]
    assert not graph.support_for("claim-budget")


def test_ch6_trace_preserved_not_support(graph):
    assert graph.control_traces["claim-redis"]
    support_targets = {e.target
                       for e in graph.support_for("claim-redis")}
    assert not support_targets


# -- evaluation ----------------------------------------------------------

def test_support_scorer():
    out = support_scores({("a", "s1")}, {("a", "s1"), ("a", "s2")})
    assert out["support_precision"] == 1.0
    assert out["support_coverage"] == 0.5


def test_provenance_precision_penalises_borrowed():
    out = provenance_precision(
        {("claim-main", "s19-benchmark"),
         ("claim-main", "s17-sqlite-case")},
        fx.ENTAILS, fx.TOPICAL_ONLY)
    assert out["provenance_precision"] == 0.5
    assert out["borrowed_count"] == 1


def test_lineage_completeness():
    traces = {"a": {"raw_grounded": True, "open_lineages": []},
              "b": {"raw_grounded": True, "open_lineages": ["x"]}}
    out = lineage_completeness(traces)
    assert out["lineage_completeness"] == 0.5
    assert out["raw_grounding_rate"] == 1.0


def test_group_validity_exact():
    out = group_validity(
        {"c": [frozenset({"a", "b"})]},
        {"c": [frozenset({"a", "b"}), frozenset({"c", "d"})]})
    assert out["group_exact_match_rate"] == 1.0


def test_echo_scores():
    out = echo_scores({"e1"}, {"e1", "e2"}, {"i1"}, {"i1"})
    assert out["echo_recall"] == 0.5
    assert out["echo_inflation_count"] == 0
    inflated = echo_scores({"e1"}, {"e1", "e2"}, {"e1", "i1"}, {"i1"})
    assert inflated["echo_inflation_count"] == 1


def test_error_localisation_scorer():
    out = error_localisation({"c": "summary"}, {"c": "summary"})
    assert out["error_localisation_accuracy"] == 1.0


def test_impact_scorer():
    out = impact_scores({"a"}, {"a", "b"})
    assert out["impact_recall"] == 0.5
    assert out["impact_precision"] == 1.0


def test_divergence_cells():
    cells = answer_evidence_divergence(fx.DIVERGENCE_CASES)
    assert cells["correct_answer_wrong_evidence"] == 1
    assert sum(cells.values()) == 4


# -- suite ----------------------------------------------------------------

def test_suite_runs_offline():
    report = run_suite()
    assert set(report["experiments"]) == {
        "E7-A", "E7-B", "E7-C", "E7-D", "E7-E",
        "E7-F", "E7-G", "E7-H", "E7-I", "E7-J"}
    assert report["costs"]["llm_calls"] == 0
