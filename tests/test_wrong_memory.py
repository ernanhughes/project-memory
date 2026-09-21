"""Model-free tests for wrong-memory probes and classification.

No API calls: probe view construction, skip rules, alias identities,
hygiene of constructed content, and the SENSITIVE/INSENSITIVE gate
on synthetic outcomes.
"""

from simulator import muse_ladder as ml
from simulator import run as run_mod
from simulator import wrong_memory as wm


def _inputs():
    data = run_mod.build_inputs()
    return data["world"], data["tasks"], data["views"]


def _task_views(views, task):
    return [v for v in views if v["date"] <= task.as_of]


def test_aliases_reuse_frozen_contexts():
    world, tasks, views = _inputs()
    task = tasks[0]
    tv = _task_views(views, task)
    assert ml.build_context("W0", tv, task, world) == \
        ml.build_context("C0", tv, task, world)
    assert ml.build_context("WC", tv, task, world) == \
        ml.build_context("CO", tv, task, world)


def test_ws_needs_superseded_history():
    world, tasks, views = _inputs()
    seen_ok = seen_skip = 0
    for task in tasks:
        tv = _task_views(views, task)
        probed, note = wm.probe_views("WS", task, tv, world)
        if probed is None:
            assert note == wm.SKIP_NO_SUPERSEDED
            seen_skip += 1
        else:
            seen_ok += 1
    assert seen_ok >= 1 and seen_skip >= 1


def test_wm_puts_superseded_first():
    world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    tv = _task_views(views, task)
    probed, note = wm.probe_views("WM", task, tv, world)
    assert probed is not None and note == "superseded-first-misleading-order"
    assert probed[0]["display_id"] == "adr-003"
    assert probed[-1]["display_id"] == "adr-007"


def test_wr_designates_supporting_evidence():
    world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    tv = _task_views(views, task)
    probed, note = wm.probe_views("WR", task, tv, world)
    assert probed is not None
    assert note.startswith("designated-revoked:")
    assert len(probed) == 1


def test_constructed_probes_look_plausible_not_announced():
    world, tasks, views = _inputs()
    task = tasks[0]
    tv = _task_views(views, task)
    for cond in ("WX", "WP"):
        probed, _note = wm.probe_views(cond, task, tv, world)
        assert probed is not None and len(probed) == 1
        body = probed[0]["body"].lower()
        for term in ("supported_by", "derived_from", "supersedes",
                     "valid_from", "oracle", "expected answer", "as_of",
                     "poison", "adversarial", "probe", "quarantine"):
            assert term not in body, (cond, term)


def test_wx_names_scope_in_text():
    world, tasks, views = _inputs()
    task = tasks[0]
    probed, _ = wm.probe_views("WX", task, _task_views(views, task),
                               world)
    assert "atlas" in probed[0]["body"].lower()


def test_wo_contains_decision_plus_support():
    world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    tv = _task_views(views, task)
    probed, _ = wm.probe_views("WO", task, tv, world)
    ids = [v["display_id"] for v in probed]
    assert "adr-007" in ids and len(ids) > 1


def test_classification_gate():
    assert wm.classify_task(1.0, 0.0, {"WS": (0.0, 0)})[0] == "SENSITIVE"
    assert wm.classify_task(1.0, 0.0, {"WS": (0.0, 1)})[0] == "SENSITIVE"
    assert wm.classify_task(1.0, 0.0, {"WS": (1.0, 0)})[0] == "INSENSITIVE"
    assert wm.classify_task(0.0, 0.0, {"WS": (0.0, 0)})[0] == "NOT-DEPENDENT"
    assert wm.classify_task(1.0, 1.0, {"WS": (0.0, 0)})[0] == "NOT-DEPENDENT"


def test_skip_rows_never_enter_means():
    rows = [
        {"condition": "WS", "task_score": 1.0, "harmful": 0},
        {"condition": "WS", "task_score": None, "harmful": 0},
    ]
    summary = ml.summarize(rows)
    assert summary["WS"]["n"] == 1
    assert summary["WS"]["task_success"] == 1.0
    assert summary["WS"]["skipped"] == 1
