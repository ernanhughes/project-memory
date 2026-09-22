"""Trust fixture gate-match: expected FULL admission holds per fixture."""

from context_frames import trust_fixtures as tfx
from context_frames import trust_policy as tp


def _units(fixture):
    return [tp.Unit(uid, kind, proj, date, text, claim, art, vf, vu,
                    tuple(der), tuple(ref), rev, res)
            for (uid, kind, proj, date, text, claim, art, vf, vu, der,
                 ref, rev, res) in fixture.units]


def _task(fixture):
    return tp.TaskPacket(fixture.behavior_task, fixture.query,
                         fixture.as_of, fixture.project,
                         fixture.caller_scope, fixture.consequential)


def _check(fixture):
    res = tp.apply_policy(_units(fixture), _task(fixture), "FULL")
    want = dict(fixture.expected)
    bad = [(uid, res.admissions[uid].verdict, res.admissions[uid].reason)
           for uid, verdict in want.items()
           if res.admissions[uid].verdict != verdict]
    return bad


def test_dev_fixtures_match_expected_full_admission():
    bad = {}
    for f in tfx.dev_fixtures():
        mism = _check(f)
        if mism:
            bad[f.fixture_id] = mism
    assert not bad, bad


def test_eval_fixtures_match_expected_full_admission():
    bad = {}
    for f in tfx.eval_fixtures():
        mism = _check(f)
        if mism:
            bad[f.fixture_id] = mism
    assert not bad, bad


def test_expected_covers_every_unit():
    for f in tfx.all_fixtures():
        assert {u[0] for u in f.units} == {uid for uid, _ in f.expected}, \
            f.fixture_id


def test_split_digests_stable_and_disjoint():
    dig = tfx.split_digests()
    assert dig["dev_count"] == 8 and dig["eval_count"] == 8
    assert dig["dev"] != dig["eval"]
