"""Separation stage-attribution tests for C6 trust admission.

Each test proves WHICH machinery fires, not just the verdict. The
composition contract: stale is denied only via validity (C3's
concern surfacing), foreign only via scope (C4's), frame
manipulations change nothing (no frame inputs exist), while
revoked/poison/low-authority/conflict resolve only via
trust-discriminating stages. If any other stage fires on these
fixtures, the layer is leaking across its boundary.
"""

import dataclasses

from simulator import run as run_mod
from simulator import trust_gate as tg


def _inputs():
    data = run_mod.build_inputs()
    return data["world"], data["tasks"], data["views"]


def _ledger_maps(world):
    by_display, by_key = {}, {}
    for record in world.ledger.records:
        by_key[record.key] = record
        if record.display_id:
            by_display[record.display_id] = record
        if record.second_display_id:
            by_display[record.second_display_id] = record
    return by_display, by_key


def _run_level(views, world, task, level):
    by_display, by_key = _ledger_maps(world)
    units = tg.units_from_views(views, by_display, by_key, {})
    packet = tg.task_packet(task)
    return tg.admit(units, packet, level)


def _event_store_task():
    _world, tasks, _views = _inputs()
    return next(t for t in tasks if t.topic == "event-store backend")


def _views_for(task):
    _world, _tasks, views = _inputs()
    return [v for v in views if v["date"] <= task.as_of]


def test_stale_denied_only_via_validity():
    world, tasks, views = _inputs()
    task = _event_store_task()
    tv = _views_for(task)
    stale = [v for v in tv if v["display_id"] == "adr-003"]
    assert stale
    res = _run_level(tv, world, task, "FULL")
    adm = res["adr-003"]
    assert adm.verdict == "deny"
    assert adm.reason == "deny.superseded_as_current"
    assert adm.stage == "validity"


def test_foreign_denied_only_via_scope():
    world, tasks, views = _inputs()
    task = _event_store_task()
    tv = _views_for(task)
    foreign = dict(tv[0])
    foreign["display_id"] = "adr-901"
    foreign["project"] = "atlas"
    res = _run_level(tv + [foreign], world, task, "FULL")
    adm = res["adr-901"]
    assert adm.verdict == "deny"
    assert adm.reason == "deny.cross_scope"
    assert adm.stage == "scope"


def test_frame_reordering_changes_nothing():
    # No frame inputs exist on Unit/TaskPacket: structural
    # frame-blindness. Reordering must not move a single verdict.
    import dataclasses as _dc
    fields = {f.name for f in _dc.fields(tg.tp.Unit)}
    assert not (fields & {"frame", "work_type", "framing", "rank"})
    tfields = {f.name for f in _dc.fields(tg.tp.TaskPacket)}
    assert not (tfields & {"frame", "work_type"})
    world, tasks, views = _inputs()
    task = _event_store_task()
    tv = _views_for(task)
    base = _run_level(tv, world, task, "FULL")
    rev = _run_level(list(reversed(tv)), world, task, "FULL")
    assert {u: (a.verdict, a.reason) for u, a in base.items()} == \
        {u: (a.verdict, a.reason) for u, a in rev.items()}


def test_revoked_denied_only_via_revocation():
    world, tasks, views = _inputs()
    task = _event_store_task()
    tv = _views_for(task)
    by_display, by_key = _ledger_maps(world)
    units = tg.units_from_views(tv, by_display, by_key,
                                {"revoked": ["session-019"]})
    packet = tg.task_packet(task)
    res = tg.admit(units, packet, "FULL")
    adm = res["session-019"]
    assert adm.verdict == "deny"
    assert adm.reason == "deny.revoked_source"
    assert adm.stage == "revocation"


def test_poison_denied_only_via_instruction():
    from simulator import wrong_memory as wm
    world, tasks, views = _inputs()
    task = _event_store_task()
    tv = _views_for(task)
    pool, _note, meta = wm.trust_probe_views("TP", task, tv, world)
    by_display, by_key = _ledger_maps(world)
    units = tg.units_from_views(pool, by_display, by_key, meta)
    packet = tg.task_packet(task)
    res = tg.admit(units, packet, "FULL")
    adm = res["session-902"]
    assert adm.verdict == "deny"
    assert adm.reason == "deny.memory_instruction"
    assert adm.stage == "instruction-refuted"


def test_preference_denied_only_via_authority():
    world, tasks, views = _inputs()
    task = _event_store_task()
    tv = _views_for(task)
    by_display, by_key = _ledger_maps(world)
    units = tg.units_from_views(tv, by_display, by_key, {})
    yoga = [u for u in units if u.unit_id == "session-033"]
    assert yoga
    packet = tg.task_packet(task)
    res = tg.admit(units, packet, "FULL")
    adm = res["session-033"]
    assert adm.verdict == "deny"
    assert adm.reason == "deny.untrusted_source"
    assert adm.stage == "authority"


def test_corroborated_conflict_quarantined_only_via_conflict():
    from simulator import wrong_memory as wm
    world, tasks, views = _inputs()
    task = _event_store_task()
    tv = _views_for(task)
    pool, _note, meta = wm.trust_probe_views("TX", task, tv, world)
    by_display, by_key = _ledger_maps(world)
    units = tg.units_from_views(pool, by_display, by_key, meta)
    packet = tg.task_packet(task)
    res = tg.admit(units, packet, "FULL")
    quarantined = sorted(uid for uid, a in res.items()
                         if a.verdict == "quarantine")
    assert quarantined, "corroborated conflict must quarantine"
    for uid in quarantined:
        assert res[uid].reason == "quarantine.conflicting_evidence"
        assert res[uid].stage == "conflict"


def test_echo_of_present_revoked_source_admitted_gap():
    # Known trust-policy gap, pinned (not patched here): revocation
    # of a PRESENT source does not propagate to its derivations.
    # _grounded checks kinds, _established checks currency — neither
    # consults revoked. T7 must add revocation inheritance; this test
    # names the gap so the port cannot silently inherit it.
    from simulator import trust_gate as _tg
    _tp = _tg.tp
    src = _tp.Unit("adr-007", "decision", "main", "2024-07-11",
                   "Target PostgreSQL.", "target PostgreSQL", "adr",
                   "2024-07-11", "", (), (), True, "")
    echo = _tp.Unit("runbook-006", "derived_restatement", "main",
                    "2024-08-16", "Operators note: target PostgreSQL.",
                    "target PostgreSQL", "runbook", "", "",
                    ("adr-007",), (), False, "")
    packet = _tp.TaskPacket("t", "q", "2024-08-23", "main", "agent",
                            True)
    res = _tp.apply_policy([src, echo], packet, "FULL")
    assert res.admissions["adr-007"].verdict == "deny"
    assert res.admissions["runbook-006"].verdict == "admit"
