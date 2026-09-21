"""Model-free tests for the Muse ladder harness (next4).

No API calls here: parsing, deterministic context construction,
session isolation, and the C3-C7 refusal. Live behavior is covered
only by frozen runs with manifests.
"""

from simulator import muse_ladder as ml
from simulator import run as run_mod


def _inputs():
    data = run_mod.build_inputs()
    return data["world"], data["tasks"], data["views"]


def test_parse_action_ok():
    assert ml.parse_action("TARGET: PostgreSQL") == {
        "target": "PostgreSQL", "parse": "ok"}


def test_parse_action_case_and_quotes():
    assert ml.parse_action("target: 'SQLite'\nnote")["target"] == "SQLite"


def test_parse_action_failure_abstains():
    assert ml.parse_action("I think PostgreSQL")["target"] == "unknown"
    assert ml.parse_action("")["parse"] == "failed"


def test_c0_has_no_history():
    world, tasks, views = _inputs()
    ctx = ml.build_context("C0", views, tasks[0], world)
    assert "adr-" not in ctx and "session-" not in ctx


def test_c1_contains_full_history():
    world, tasks, views = _inputs()
    ctx = ml.build_context("C1", views, tasks[0], world)
    assert "adr-007" in ctx and "SQLite" in ctx


def test_c2_is_topk_subset_of_c1():
    world, tasks, views = _inputs()
    task_views = [v for v in views if v["date"] <= tasks[0].as_of]
    c1 = ml.build_context("C1", task_views, tasks[0], world)
    c2 = ml.build_context("C2", task_views, tasks[0], world)
    assert len(c2) < len(c1)
    assert c2.count("\n\n---\n\n") + 1 == ml.LEXICAL_K


def test_co_contains_current_decision_only():
    world, tasks, views = _inputs()
    task = next(t for t in tasks if t.topic == "event-store backend")
    task_views = [v for v in views if v["date"] <= task.as_of]
    co = ml.build_context("CO", task_views, task, world)
    assert "adr-007" in co
    assert "adr-003" not in co


def test_unbuilt_conditions_refuse():
    world, tasks, views = _inputs()
    for cond in ("C3", "C4", "C5", "C6", "C7"):
        try:
            ml.build_context(cond, views, tasks[0], world)
        except NotImplementedError:
            pass
        else:
            raise AssertionError(f"{cond} must refuse")


def test_session_unique_per_call():
    a = ml.session_for("run1", "task-x", "C0")
    b = ml.session_for("run1", "task-x", "C1")
    c = ml.session_for("run1", "task-x", "C0", repeat=1)
    assert len({a, b, c}) == 3


def test_prompt_carries_full_context_every_call():
    world, tasks, views = _inputs()
    ctx = ml.build_context("C1", views, tasks[0], world)
    prompt = ml.build_prompt(tasks[0], ctx)
    assert tasks[0].text in prompt and "adr-007" in prompt
