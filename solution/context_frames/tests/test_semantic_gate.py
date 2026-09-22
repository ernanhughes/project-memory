"""Tests for the semantic gate and its fixtures (gate v2, Chapter 13)."""

from context_frames import semantic_fixtures as sfx
from context_frames import semantic_gate as sg
from evidence_lineage import reconciliation as R
from evidence_lineage.lineage import LineageGraph, Node, NodeKind


def _build(scenario):
    g = LineageGraph()
    for nid, date, proj, until, contra, ref in scenario.nodes:
        payload = (("date", date), ("project", proj))
        if until:
            payload += (("valid_until", until),)
        if contra:
            payload += (("contradicts", contra),)
        if ref:
            payload += (("references", ref),)
        g.add_node(Node(nid, NodeKind.SOURCE_SPAN, payload=payload))
    rset = R.ReconciliationSet()
    for rid, a, b, rel, standpoint, auth, resolves, refs in scenario.recs:
        rset.add(R.Reconciliation(
            rid, a, b, R.Relationship(rel), standpoint, auth,
            tuple(refs), resolves_conflict=resolves), g)
    later = tuple(R.LaterEvent(d, k, s, n)
                  for d, k, s, n in scenario.later)
    return g, rset, later


def _decide(scenario):
    g, rset, later = _build(scenario)
    return sg.decide_for_subject(
        g, rset, scenario.frame_subject, scenario.as_of,
        scenario.needs_memory, scenario.consequential,
        scenario.abstention_acceptable, later=later)


# -- every dev fixture derives its pre-registered hint and action ------

def test_dev_fixtures_derive_expected_hint_and_action():
    bad = []
    for s in sfx.dev_scenarios():
        d = _decide(s)
        if (d.establishment, d.action) != (s.expected_hint, s.expected_action):
            bad.append((s.scenario_id, d.establishment, d.action))
    assert not bad, bad


# -- every eval fixture derives its pre-registered hint and action -----
# (Checked here so a broken fixture cannot reach the held-out run; the
# runner re-asserts the same on eval open. Expected values were fixed
# when fixtures were authored, before any eval recomputation.)

def test_eval_fixtures_derive_expected_hint_and_action():
    bad = []
    for s in sfx.eval_scenarios():
        d = _decide(s)
        if (d.establishment, d.action) != (s.expected_hint, s.expected_action):
            bad.append((s.scenario_id, d.establishment, d.action))
    assert not bad, bad


# -- positive-control case coverage on both splits -----------------------

def test_both_splits_cover_all_reconciliation_cases():
    for name, scenarios in (("dev", sfx.dev_scenarios()),
                            ("eval", sfx.eval_scenarios())):
        covered = {sfx.case_of(s) for s in scenarios}
        missing = [c for c in sfx.REQUIRED_CASES if c not in covered]
        assert not missing, f"{name} missing: {missing}"


# -- anti-promotion: HARD only via corroborated ---------------------------

def test_hard_requires_corroborated_on_both_splits():
    bad = []
    for s in sfx.all_scenarios():
        d = _decide(s)
        if d.action == sg.HARD_FRAME and d.establishment != "corroborated":
            bad.append(s.scenario_id)
        if d.establishment != "corroborated" and d.action == sg.HARD_FRAME:
            bad.append(s.scenario_id + ":promoted")
    assert not bad, bad


def test_correspondence_never_hard():
    for s in [x for x in sfx.all_scenarios()
              if sfx.case_of(x) == "correspondence_only"]:
        d = _decide(s)
        assert d.action != sg.HARD_FRAME, s.scenario_id
        assert d.establishment == "unknown", s.scenario_id


# -- mapping spot checks ---------------------------------------------------

def test_unknown_routing():
    g = LineageGraph()
    g.add_node(Node("s", NodeKind.SOURCE_SPAN,
                    payload=(("date", "2024-07-20"),)))
    rset = R.ReconciliationSet()
    assert (sg.decide_for_subject(g, rset, "s", "2024-08-23", True, True,
                                  True).action == sg.ABSTAIN)
    assert (sg.decide_for_subject(g, rset, "s", "2024-08-23", True, True,
                                  False).action == sg.REQUEST_MORE)
    assert (sg.decide_for_subject(g, rset, "s", "2024-08-23", True, False,
                                  False).action == sg.QUERY_ONLY)


def test_conflicting_vetoes_coexisting_corroboration():
    g = LineageGraph()
    for nid, date in (("a", "2024-07-11"), ("b", "2024-07-12"),
                      ("c", "2024-07-10")):
        g.add_node(Node(nid, NodeKind.SOURCE_SPAN,
                        payload=(("date", date),)))
    # wire contradiction marks onto a/b via fresh nodes is overkill;
    # contradict directly through payload rebuild:
    g2 = LineageGraph()
    g2.add_node(Node("a", NodeKind.SOURCE_SPAN,
                     payload=(("date", "2024-07-11"),
                              ("contradicts", "b"),)))
    g2.add_node(Node("b", NodeKind.SOURCE_SPAN,
                     payload=(("date", "2024-07-12"),
                              ("contradicts", "a"),)))
    g2.add_node(Node("c", NodeKind.SOURCE_SPAN,
                     payload=(("date", "2024-07-10"),)))
    rset = R.ReconciliationSet()
    rset.add(R.Reconciliation("r1", "a", "b", R.Relationship.SAME_EVENT,
                              "2024-07-12", "ledger", (),
                              resolves_conflict=True), g2)
    rset.add(R.Reconciliation("r2", "a", "c", R.Relationship.SAME_EVENT,
                              "2024-07-12", "ledger", (),
                              resolves_conflict=True), g2)
    d = sg.decide_for_subject(g2, rset, "a", "2024-08-23", True, True,
                              False)
    assert d.establishment == "conflicting"
    assert d.action == sg.QUERY_ONLY


def test_split_digests_stable_and_disjoint():
    dig = sfx.split_digests()
    assert dig["dev_count"] == 12 and dig["eval_count"] == 9
    assert dig["dev"] != dig["eval"]
    dev_ids = {s.scenario_id for s in sfx.dev_scenarios()}
    eval_ids = {s.scenario_id for s in sfx.eval_scenarios()}
    assert not (dev_ids & eval_ids)
