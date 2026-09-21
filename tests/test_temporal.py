"""Tests for C3 temporal filtering: repairs stale, touches nothing else."""

from simulator import run as run_mod
from simulator import temporal as temporal_mod
from simulator import wrong_memory as wm


def test_superseded_ids_known():
    data = run_mod.build_inputs()
    dropped = temporal_mod.superseded_display_ids(data["ledger"],
                                                  "2025-06-30")
    assert "adr-003" in dropped  # SQLite decision superseded 2024-07-11
    assert "adr-007" not in dropped  # current PostgreSQL decision kept


def test_filter_repairs_ws_retains_wc():
    data = run_mod.build_inputs()
    ledger = data["ledger"]
    world, tasks, views = data["world"], data["tasks"], data["views"]
    task = next(t for t in tasks if t.topic == "event-store backend")
    tv = [v for v in views if v["date"] <= task.as_of]
    ws, _ = wm.probe_views("WS", task, tv, world)
    ws_ids = {v["display_id"] for v in ws}
    assert ws_ids == {"adr-003"}
    kept = temporal_mod.temporal_filter(tv, ledger, task.as_of)
    kept_ids = {v["display_id"] for v in kept}
    assert not (ws_ids & kept_ids)  # stale-only content fully removed
    assert "adr-007" in kept_ids  # current decision retained
    assert len(kept) < len(tv)  # filter did something
    assert [v["display_id"] for v in kept] == [
        v["display_id"] for v in tv if v["display_id"] in kept_ids]


def test_filter_ignores_scope_poison_revocation():
    data = run_mod.build_inputs()
    ledger = data["ledger"]
    world, tasks, views = data["world"], data["tasks"], data["views"]
    task = tasks[0]
    tv = _task_views(views, task)
    for cond in ("WX", "WP"):
        probed, _ = wm.probe_views(cond, task, tv, world)
        ids_before = [v["display_id"] for v in probed]
        kept = temporal_mod.temporal_filter(probed, ledger, task.as_of)
        assert [v["display_id"] for v in kept] == ids_before


def _task_views(views, task):
    return [v for v in views if v["date"] <= task.as_of]
