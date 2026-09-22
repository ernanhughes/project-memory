"""Tests for frame-evidence extraction (bridge, no gate behaviour)."""

from context_frames import frame_evidence as FE
from evidence_lineage import reconciliation as R
from evidence_lineage.lineage import LineageGraph, Node, NodeKind


def _node(node_id, date, project="main", valid_until=""):
    payload = (("date", date), ("project", project))
    if valid_until:
        payload += (("valid_until", valid_until),)
    return Node(node_id, NodeKind.SOURCE_SPAN, payload=payload)


def _setup():
    g = LineageGraph()
    for n in (_node("intent-401", "2024-07-17"),
              _node("commit-118", "2024-08-27"),
              _node("adr-007", "2024-07-11"),
              _node("agent-note-1", "2024-07-20"),
              _node("adr-507", "2024-07-11", project="atlas"),
              _node("fact-301", "2024-03-04", valid_until="2024-07-22")):
        g.add_node(n)
    rset = R.ReconciliationSet()
    rset.add(R.Reconciliation("r-close", "commit-118", "intent-401",
                              R.Relationship.COMPLETES, "2024-08-27",
                              "author-merge", resolves_conflict=True), g)
    rset.add(R.Reconciliation("r-agent", "agent-note-1", "adr-007",
                              R.Relationship.SAME_EVENT, "2024-07-20",
                              "agent:reader-1", resolves_conflict=True), g)
    rset.add(R.Reconciliation("r-xscope", "adr-007", "adr-507",
                              R.Relationship.SAME_EVENT, "2024-07-11",
                              "agent:reader-1", resolves_conflict=True), g)
    rset.add(R.Reconciliation("r-old", "fact-301", "adr-007",
                              R.Relationship.SAME_EVENT, "2024-07-11",
                              "ledger", resolves_conflict=True), g)
    return g, rset


def test_ledger_completion_yields_corroborated():
    g, rset = _setup()
    hints = FE.establishment_hints_for(g, rset, "intent-401", "2024-08-30")
    assert [(h["hint"], h["basis"]) for h in hints] == [
        ("corroborated", ["r-close"])]


def test_agent_authority_yields_weak():
    g, rset = _setup()
    hints = FE.establishment_hints_for(g, rset, "adr-007", "2024-08-23")
    by_basis = {h["basis"][0]: h["hint"] for h in hints}
    assert by_basis["r-agent"] == "weak"
    assert by_basis["r-xscope"] == "unknown"


def test_ended_validity_yields_stale():
    g, rset = _setup()
    hints = FE.establishment_hints_for(g, rset, "fact-301", "2024-08-23")
    assert [h["hint"] for h in hints] == ["stale"]


def test_subject_without_records_yields_no_hints():
    g, rset = _setup()
    assert FE.establishment_hints_for(g, rset, "session-999",
                                      "2024-08-23") == []


def test_hints_carry_auditable_basis():
    g, rset = _setup()
    for h in FE.establishment_hints_for(g, rset, "adr-007", "2024-08-23"):
        assert h["basis"] and h["reason"] and h["authority"]
        assert h["hint"] in FE.HINTS


def test_extraction_never_emits_policy_actions():
    g, rset = _setup()
    hints = FE.establishment_hints_for(g, rset, "intent-401", "2024-08-30")
    for h in hints:
        assert "action" not in h
        assert h["hint"] != "resolved"  # resolutions are not hints
