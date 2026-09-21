"""Model-free tests for C6 trust probes (TC/TR/TL/TP/TD/TX).

No API calls: pool construction, skip rules, probe metadata, and
the adaptation mapping. Behavioral measurement happens only in
frozen runs.
"""

from simulator import run as run_mod
from simulator import trust_gate as tg
from simulator import wrong_memory as wm


def _inputs():
    data = run_mod.build_inputs()
    return data["world"], data["tasks"], data["views"]


def _tv(views, task):
    return [v for v in views if v["date"] <= task.as_of]


def _ledger_maps(world):
    by_display, by_key = {}, {}
    for record in world.ledger.records:
        by_key[record.key] = record
        if record.display_id:
            by_display[record.display_id] = record
        if record.second_display_id:
            by_display[record.second_display_id] = record
    return by_display, by_key


def test_tc_control_benign_pool():
    world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    pool, note, meta = wm.trust_probe_views("TC", task, _tv(views, task),
                                            world)
    assert pool is not None and meta == {}
    assert "adr-007" in [v["display_id"] for v in pool]


def test_tr_single_task_with_evidence():
    world, tasks, views = _inputs()
    covered = []
    for task in tasks:
        pool, note, meta = wm.trust_probe_views(
            "TR", task, _tv(views, task), world)
        if pool is not None:
            covered.append(task.topic)
            assert meta.get("revoked"), task.task_id
    assert covered == ["event-store backend"]


def test_tl_preference_topics_only():
    world, tasks, views = _inputs()
    covered = [t.topic for t in tasks
               if wm.trust_probe_views("TL", t, _tv(views, t), world)[0]
               is not None]
    assert len(covered) == 4, covered


def test_tp_all_topics_decision_plus_poison():
    world, tasks, views = _inputs()
    for task in tasks:
        pool, note, meta = wm.trust_probe_views(
            "TP", task, _tv(views, task), world)
        assert pool is not None, task.task_id
        assert len(pool) == 2, task.task_id
        assert "session-902" in [v["display_id"] for v in pool]
        assert meta["refutes"]  # poison tied to the decision


def test_td_echo_topics_only():
    world, tasks, views = _inputs()
    covered = [t.topic for t in tasks
               if wm.trust_probe_views("TD", t, _tv(views, t), world)[0]
               is not None]
    assert len(covered) == 3, covered


def test_tx_all_topics_with_structure():
    world, tasks, views = _inputs()
    for task in tasks:
        pool, note, meta = wm.trust_probe_views(
            "TX", task, _tv(views, task), world)
        assert pool is not None, task.task_id
        assert len(pool) == 4, task.task_id
        assert meta["refutes"], task.task_id


def test_adaptation_maps_display_namespace():
    world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    pool, _note, meta = wm.trust_probe_views("TC", task,
                                             _tv(views, task), world)
    by_display, by_key = _ledger_maps(world)
    units = tg.units_from_views(pool, by_display, by_key, meta)
    assert {u.unit_id for u in units} == {
        v["display_id"] for v in pool}
    assert tg.TRUST_POLICY_VERSION == "trust-policy-v1.1"


def test_adaptation_resolves_derived_refs():
    world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    pool, _note, meta = wm.trust_probe_views("TD", task,
                                             _tv(views, task), world)
    assert pool is not None
    by_display, by_key = _ledger_maps(world)
    units = tg.units_from_views(pool, by_display, by_key, meta)
    assert len(units) == 1
    assert units[0].derived_from  # echo keeps its source ref


def test_tc_single_string_inherited_by_all_levels():
    from simulator import muse_ladder as ml
    world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    rows = ml.run_trust_probe(None, "dry", task, views, world, "TC",
                              "test-model", dry_run=True)
    by_cond = {r["condition"]: r for r in rows}
    assert set(by_cond) == {"TC-RAW", "TC-C6", "TC-S1", "TC-S2",
                            "TC-S3"}
    primaries = [c for c, r in by_cond.items()
                 if "inherited_from" not in r]
    assert len(primaries) == 1
    assert by_cond["TC-RAW"].get("inherited_from") in (None, "TC-RAW")


def test_tp_divergent_levels_get_own_strings():
    from simulator import muse_ladder as ml
    world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    rows = ml.run_trust_probe(None, "dry", task, views, world, "TP",
                              "test-model", dry_run=True)
    by_cond = {r["condition"]: r for r in rows}
    # S1 denies poison like C6 (inherit); S2/S3 admit it like RAW.
    assert by_cond["TP-S1"].get("inherited_from") == "TP-C6"
    assert by_cond["TP-S2"].get("inherited_from") == "TP-RAW"
    assert by_cond["TP-S3"].get("inherited_from") == "TP-RAW"
    assert "inherited_from" not in by_cond["TP-RAW"]
    assert "inherited_from" not in by_cond["TP-C6"]
