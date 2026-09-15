"""World A fidelity + parametric generation tests.

Every canonical fact asserted here is transcribed from
spec/running-examples.md (World A timeline, decision/production yaml,
provenance table). If the ledger changes, these tests must change with
it — they pin the transcription, not the prose.
"""

from generator.worlds import (
    TEMPLATE_NAMES,
    build_ledger,
    build_world_a,
)


def _world_a_keys():
    records, _ = build_world_a()
    return {r.key: r for r in records}


def _parametric(records, world_a_keys):
    return [r for r in records if r.key not in world_a_keys]


def test_world_a_decision_edges():
    by_key = _world_a_keys()
    evt205 = by_key["evt-205"]
    assert evt205.kind == "decision"
    assert evt205.display_id == "adr-007"
    assert evt205.date == "2024-07-11"
    assert set(evt205.supported_by) == {"evt-202", "evt-203", "evt-204"}
    assert evt205.supersedes == ("evt-201",)
    assert evt205.valid_until is None


def test_world_a_production_split():
    by_key = _world_a_keys()
    f301, f302 = by_key["fact-301"], by_key["fact-302"]
    assert (f301.valid_from, f301.valid_until) == ("2024-03-04", "2024-07-22")
    assert (f302.valid_from, f302.valid_until) == ("2024-07-22", None)
    assert f302.supersedes == ("fact-301",)
    assert by_key["evt-201"].valid_until == "2024-07-11"


def test_world_a_trap_roles():
    by_key = _world_a_keys()
    kinds = {}
    for r in by_key.values():
        for did in (r.display_id, r.second_display_id):
            if did in ("session-031", "session-033", "adr-007"):
                kinds[did] = r.kind
    assert kinds == {
        "session-031": "proposal",
        "session-033": "preference",
        "adr-007": "decision",
    }


def test_world_a_echo_edge():
    by_key = _world_a_keys()
    assert by_key["evt-207"].derived_from == ("evt-205",)
    assert by_key["evt-207"].kind == "derived_restatement"


def test_world_a_uses_only_template_scenarios():
    by_key = _world_a_keys()
    assert {r.scenario for r in by_key.values()} <= set(TEMPLATE_NAMES)


def test_parametric_worlds_cover_all_templates():
    ledger, _, _ = build_ledger(12, seed=20240823)
    wa = _world_a_keys()
    scenarios = {r.scenario for r in _parametric(ledger.records, wa)}
    assert scenarios == set(TEMPLATE_NAMES)


def test_parametric_topics_unique_and_disjoint_from_world_a():
    ledger, _, _ = build_ledger(12, seed=20240823)
    wa = _world_a_keys()
    world_a_topics = {r.topic for r in wa.values()}
    param_topics = [r.topic for r in _parametric(ledger.records, wa)]
    assert len(set(param_topics)) == 12
    assert not (set(param_topics) & world_a_topics)


def test_supporting_evidence_predates_decisions():
    ledger, _, _ = build_ledger(12, seed=20240823)
    by_key = {r.key: r for r in ledger.records}
    for r in ledger.records:
        for ref in r.supported_by:
            assert by_key[ref].date <= r.date, (r.key, ref)
