"""Tests for C4 scope filtering: excludes foreign, touches nothing else."""

from simulator import run as run_mod
from simulator import scope as scope_mod
from simulator import wrong_memory as wm


def _inputs():
    data = run_mod.build_inputs()
    return data["world"], data["tasks"], data["views"]


def test_foreign_views_excluded_everywhere():
    _world, tasks, views = _inputs()
    task = tasks[0]
    tv = [v for v in views if v["date"] <= task.as_of]
    probed, _ = wm.probe_views("WX", task, tv, _world)
    assert probed[0].get("project") == "atlas"
    kept = scope_mod.scope_filter(tv + probed, task.project)
    assert [v["display_id"] for v in kept] == [
        v["display_id"] for v in tv]


def test_metadata_only_foreign_excluded():
    _world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    tv = [v for v in views if v["date"] <= task.as_of]
    probed, note = wm.probe_views("WXm", task, tv, _world)
    assert probed is not None, note
    assert "atlas" not in probed[0]["body"].lower()
    kept = scope_mod.scope_filter(tv + probed, task.project)
    assert "adr-903" not in [v["display_id"] for v in kept]


def test_wxm_coverage_documented():
    _world, tasks, views = _inputs()
    covered = []
    for task in tasks:
        tv = [v for v in views if v["date"] <= task.as_of]
        probed, _note = wm.probe_views("WXm", task, tv, _world)
        if probed is not None:
            covered.append(task.topic)
    # Stale-targeted (3) plus losing-option (3) topics; the rest have
    # no wrong option in-ledger and are skipped by construction.
    assert len(covered) == 6, covered


def test_stale_poison_revoked_pass_through():
    _world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    tv = [v for v in views if v["date"] <= task.as_of]
    ws, _ = wm.probe_views("WS", task, tv, _world)
    wp, _ = wm.probe_views("WP", task, tv, _world)
    for probed in (ws, wp):
        kept = scope_mod.scope_filter(probed, task.project)
        assert [v["display_id"] for v in kept] == [
            v["display_id"] for v in probed]


def test_full_history_unchanged_single_project():
    _world, tasks, views = _inputs()
    for task in tasks:
        tv = [v for v in views if v["date"] <= task.as_of]
        assert scope_mod.scope_filter(tv, task.project) == tv
