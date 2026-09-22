"""Tests for ledger reconciliation as evidence (Chapters 7-8 grounding).

Conventions mirror test_evidence_lineage.py: plain pytest, small inline
builders, no markers. Every adversarial case asserts the anti-collapse
rule: relating two records must never manufacture current truth.
"""

import pytest

from evidence_lineage import reconciliation as R
from evidence_lineage.lineage import LineageGraph, Node, NodeKind


def _node(node_id, date, project="main", valid_until="", contradicts="",
          references=""):
    payload = (("date", date), ("project", project))
    if valid_until:
        payload += (("valid_until", valid_until),)
    if contradicts:
        payload += (("contradicts", contradicts),)
    if references:
        payload += (("references", references),)
    return Node(node_id, NodeKind.SOURCE_SPAN, payload=payload)


def _graph(*nodes):
    g = LineageGraph()
    for n in nodes:
        g.add_node(n)
    return g


def _rec(rec_id, a, b, rel=R.Relationship.SAME_EVENT, standpoint="2024-08-27",
        authority="author-merge", resolves=True):
    return R.Reconciliation(rec_id, a, b, rel, standpoint, authority,
                            resolves_conflict=resolves)


def _resolved_set(graph, rec):
    rset = R.ReconciliationSet()
    rset.add(rec, graph)
    return rset


# -- happy paths: relationship holds, truth untouched ------------------

def test_same_event_resolves_without_asserting_truth():
    g = _graph(_node("session-051", "2024-07-17"),
               _node("commit-118", "2024-08-27"))
    rec = _rec("r1", "session-051", "commit-118")
    out = _resolved_set(g, rec).resolve(g, "r1", "2024-08-30")
    assert out["resolution"] == "resolved"
    assert out["relationship"] == "same_event"
    assert "truth" not in out and "content" not in out


def test_completes_resolves_obligation_closure():
    g = _graph(_node("intent-401", "2024-07-17"),
               _node("commit-118", "2024-08-27"))
    rec = _rec("r1", "commit-118", "intent-401",
               rel=R.Relationship.COMPLETES)
    out = _resolved_set(g, rec).resolve(g, "r1", "2024-08-30")
    assert out["resolution"] == "resolved"


def test_correspondence_only_never_evaluates():
    g = _graph(_node("session-014", "2024-06-14"),
               _node("session-019", "2024-06-19"))
    rec = _rec("r1", "session-014", "session-019",
               rel=R.Relationship.CORRESPONDENCE, resolves=False)
    out = _resolved_set(g, rec).resolve(g, "r1", "2027-06-30")
    assert out["resolution"] == "correspondence_only"


# -- adversarial: stale -------------------------------------------------

def test_stale_validity_refuses_resolution():
    g = _graph(_node("adr-003", "2024-03-01", valid_until="2024-07-11"),
               _node("evt-205", "2024-07-11"))
    rec = _rec("r1", "adr-003", "evt-205", standpoint="2024-07-11")
    out = _resolved_set(g, rec).resolve(g, "r1", "2024-08-23")
    assert out["resolution"] == "stale"


def test_validity_covering_as_of_still_resolves():
    g = _graph(_node("adr-003", "2024-03-01", valid_until="2024-07-11"),
               _node("evt-205", "2024-07-11"))
    rec = _rec("r1", "adr-003", "evt-205", standpoint="2024-07-11")
    out = _resolved_set(g, rec).resolve(g, "r1", "2024-07-11")
    assert out["resolution"] == "resolved"


# -- adversarial: contradictory records ---------------------------------

def test_contradictory_subjects_refused_not_merged():
    g = _graph(_node("claim-a", "2024-07-11", contradicts="claim-b"),
               _node("claim-b", "2024-07-12", contradicts="claim-a"))
    rec = _rec("r1", "claim-a", "claim-b", standpoint="2024-07-12")
    out = _resolved_set(g, rec).resolve(g, "r1", "2024-08-23")
    assert out["resolution"] == "conflict"


def test_one_sided_reference_is_not_mutual_contradiction():
    # A references B; B is silent. The pair may still resolve, and the
    # resolution entails nothing about B on its own: statuses attach
    # to the pair, never to a subject's content.
    g = _graph(_node("claim-a", "2024-07-11", references="claim-b"),
               _node("claim-b", "2024-07-12"))
    rec = _rec("r1", "claim-a", "claim-b", standpoint="2024-07-12")
    out = _resolved_set(g, rec).resolve(g, "r1", "2024-08-23")
    assert out["resolution"] == "resolved"
    assert "claim-b" not in out["detail"] or "content" not in out


def test_one_sided_contradiction_mark_still_blocks():
    # A contradiction mark in either direction contests the pair: a
    # resolving record over a contested pair is refused, not merged.
    g = _graph(_node("claim-a", "2024-07-11", contradicts="claim-b"),
               _node("claim-b", "2024-07-12"))
    rec = _rec("r1", "claim-a", "claim-b", standpoint="2024-07-12")
    out = _resolved_set(g, rec).resolve(g, "r1", "2024-08-23")
    assert out["resolution"] == "conflict"


# -- adversarial: cross-project ------------------------------------------

def test_cross_project_without_licence_quarantined():
    g = _graph(_node("adr-007", "2024-07-11", project="main"),
               _node("adr-507", "2024-07-11", project="atlas"))
    rec = _rec("r1", "adr-007", "adr-507", authority="agent:reader-1",
               standpoint="2024-07-11")
    out = _resolved_set(g, rec).resolve(g, "r1", "2024-08-23")
    assert out["resolution"] == "cross_scope"


def test_cross_project_with_explicit_licence_proceeds():
    g = _graph(_node("adr-007", "2024-07-11", project="main"),
               _node("adr-507", "2024-07-11", project="atlas"))
    rec = _rec("r1", "adr-007", "adr-507", authority="author-merge",
               standpoint="2024-07-11")
    out = _resolved_set(g, rec).resolve(g, "r1", "2024-08-23")
    assert out["resolution"] == "resolved"


# -- adversarial: later invalidation -------------------------------------

def test_revocation_after_standpoint_invalidates():
    g = _graph(_node("session-508", "2024-06-19"),
               _node("runbook-509", "2024-08-02"))
    rec = _rec("r1", "session-508", "runbook-509", standpoint="2024-08-02")
    rset = _resolved_set(g, rec)
    ev = R.LaterEvent("2024-09-01", "revocation", "session-508", "withdrawn")
    assert (rset.resolve(g, "r1", "2024-10-01", later=(ev,))
            ["resolution"] == "invalidated")


def test_revocation_outside_window_ignored():
    g = _graph(_node("session-508", "2024-06-19"),
               _node("runbook-509", "2024-08-02"))
    rec = _rec("r1", "session-508", "runbook-509", standpoint="2024-08-02")
    rset = _resolved_set(g, rec)
    ev = R.LaterEvent("2024-10-01", "revocation", "session-508", "withdrawn")
    assert (rset.resolve(g, "r1", "2024-09-01", later=(ev,))
            ["resolution"] == "resolved")


def test_supersession_after_standpoint_invalidates():
    g = _graph(_node("fact-301", "2024-03-04"),
               _node("session-031", "2024-07-08"))
    rec = _rec("r1", "fact-301", "session-031", standpoint="2024-07-08")
    rset = _resolved_set(g, rec)
    ev = R.LaterEvent("2024-07-22", "supersession", "fact-301", "pg live")
    assert (rset.resolve(g, "r1", "2024-08-23", later=(ev,))
            ["resolution"] == "invalidated")


def test_as_of_before_standpoint_invalidated():
    g = _graph(_node("a", "2024-07-11"), _node("b", "2024-07-12"))
    rec = _rec("r1", "a", "b", standpoint="2024-07-12")
    out = _resolved_set(g, rec).resolve(g, "r1", "2024-07-01")
    assert out["resolution"] == "invalidated"


# -- add-time structural rules --------------------------------------------

def test_correspondence_claiming_resolution_rejected():
    g = _graph(_node("a", "2024-07-11"), _node("b", "2024-07-12"))
    with pytest.raises(ValueError):
        _resolved_set(
            g, _rec("r1", "a", "b",
                    rel=R.Relationship.CORRESPONDENCE, resolves=True))


def test_standpoint_before_subject_rejected():
    g = _graph(_node("a", "2024-07-11"), _node("b", "2024-07-12"))
    with pytest.raises(ValueError):
        _resolved_set(g, _rec("r1", "a", "b", standpoint="2024-07-01"))


def test_unknown_subject_rejected():
    g = _graph(_node("a", "2024-07-11"))
    with pytest.raises(ValueError):
        _resolved_set(g, _rec("r1", "a", "ghost"))


def test_self_relating_rejected():
    g = _graph(_node("a", "2024-07-11"))
    with pytest.raises(ValueError):
        _resolved_set(g, _rec("r1", "a", "a"))


def test_duplicate_rec_id_rejected():
    g = _graph(_node("a", "2024-07-11"), _node("b", "2024-07-12"))
    rset = R.ReconciliationSet()
    rset.add(_rec("r1", "a", "b"), g)
    with pytest.raises(ValueError):
        rset.add(_rec("r1", "a", "b"), g)


def test_missing_authority_rejected():
    g = _graph(_node("a", "2024-07-11"), _node("b", "2024-07-12"))
    with pytest.raises(ValueError):
        _resolved_set(g, _rec("r1", "a", "b", authority=""))


# -- anti-collapse: verification path untouched -----------------------------

def test_resolved_reconciliation_does_not_verify_claims():
    from evidence_lineage import fixtures as fx
    from evidence_lineage.evidence import claim_support_status
    supports = fx.build_supports()
    before = claim_support_status(supports["claim-atomic"], fx.ENTAILS)
    g = fx.build_graph()
    rset = R.ReconciliationSet()
    nodes = list(g.nodes)[:2]
    rset.add(_rec("r1", nodes[0], nodes[1]), g)
    out = rset.resolve(g, "r1", "2027-06-30")
    after = claim_support_status(supports["claim-atomic"], fx.ENTAILS)
    assert before == after
    assert out["resolution"] in ("resolved", "correspondence_only")
