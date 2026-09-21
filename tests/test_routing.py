"""Tests for question-type routing (recall vs influence boundary).

No model calls: route table pins, admission differences on fixture
data, and the q-000018 mechanism (authority must not erase recall).
"""

from simulator import pipeline as pipe_mod
from simulator import run as run_mod


def _inputs():
    data = run_mod.build_inputs()
    return data["world"], data["tasks"], data["views"]


def test_routes_pinned():
    assert pipe_mod.route_for("Q1") == ("retrieval", "temporal")
    assert pipe_mod.route_for("Q-recall") == ("retrieval", "temporal")
    assert pipe_mod.route_for("Q2") == ("retrieval", "temporal")
    assert pipe_mod.route_for("Q5") == ("retrieval", "temporal")
    assert "trust" in pipe_mod.route_for("new-service")
    assert "assembly" in pipe_mod.route_for("new-service")
    assert pipe_mod.route_for("Q-irr") == ()
    try:
        pipe_mod.route_for("Q9")
    except ValueError:
        pass
    else:
        raise AssertionError("unrouted family must raise")


def test_recall_route_keeps_preference_q000018():
    # The expansion loss, structurally: message-queue preference
    # session-1005 is denied by trust admission (authority) but must
    # survive recall routing (historical visibility).
    world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "message-queue backend")
    tv = [v for v in views if v["date"] <= task.as_of]
    kept, trace = pipe_mod.routed_admission(tv, world, task, "Q1")
    assert trace["route"] == ["retrieval", "temporal"]
    assert "session-1005" in [v["display_id"] for v in kept]
    full, _trace = pipe_mod.integrated_views(tv, world, task)
    assert "session-1005" not in [v["display_id"] for v in full]


def test_control_route_admits_nothing():
    world, tasks, views = _inputs()
    task = tasks[0]
    tv = [v for v in views if v["date"] <= task.as_of]
    kept, trace = pipe_mod.routed_admission(tv, world, task, "Q-irr")
    assert kept == []
    assert trace["route"] == []


def test_action_route_matches_integrated():
    world, tasks, views = _inputs()
    task = tasks[0]
    tv = [v for v in views if v["date"] <= task.as_of]
    kept, trace = pipe_mod.routed_admission(
        tv, world, task, "new-service")
    full, _trace = pipe_mod.integrated_views(tv, world, task)
    assert [v["display_id"] for v in kept] == [
        v["display_id"] for v in full]
    assert "trust" in trace
