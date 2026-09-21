"""Model-free tests for expansion tasks, qeval, and E-branch dry runs."""

from simulator import expansion as exp_mod
from simulator import expansion_run as exprun_mod
from simulator import pipeline as pipe_mod
from simulator import qeval as qeval_mod
from simulator import run as run_mod


def _ledger():
    from generator import build as build_mod
    return build_mod.build_corpus()["ledger"]


def test_q1q2_reuse_frozen_contract():
    tasks = exp_mod.q1q2_tasks()
    assert len(tasks) == 6
    assert {t.query_kind for t in tasks} == {"ids"}
    assert all(t.expected_ids for t in tasks)


def test_q3_q4_q5_counts():
    ledger = _ledger()
    assert len(exp_mod.q3_tasks(ledger)) == 2
    assert len(exp_mod.q4_tasks()) == 2
    assert len(exp_mod.q5_tasks()) == 2
    assert exp_mod.q4_tasks()[0].expected_bool is True
    assert exp_mod.q4_tasks()[1].expected_bool is False


def test_recall_expected_ids():
    task = exp_mod.recall_task()
    assert task.expected_ids == ("session-014", "session-019",
                                 "session-031", "session-033")


def test_qeval_parse_score():
    assert qeval_mod.parse_ids("session-014\nadr-007\nsession-014") == [
        "session-014", "adr-007"]
    assert qeval_mod.parse_yesno("YES, it is.") is True
    assert qeval_mod.parse_yesno("no.") is False
    assert qeval_mod.parse_yesno("maybe") is None
    assert qeval_mod.parse_yesno("no.") is False
    assert qeval_mod.parse_yesno("maybe") is None

    class T:
        query_kind = "ids"
        expected_ids = ("a-1",)
    assert qeval_mod.score_qtask(T(), "a-1")["task_score"] == 1.0
    assert qeval_mod.score_qtask(T(), "a-2")["task_score"] == 0.0


def test_qeval_id_scoring_order_insensitive():
    class T:
        query_kind = "ids"
        expected_ids = ("a-1", "a-2")

    class T2:
        query_kind = "ids"
        expected_ids = ("incident-021", "session-014", "session-019")
    assert qeval_mod.score_qtask(T(), "a-2\na-1")["task_score"] == 1.0
    assert qeval_mod.score_qtask(
        T2(), "session-014\nsession-019\nincident-021")[
            "task_score"] == 1.0
    assert qeval_mod.score_qtask(T2(), "session-014")[
        "task_score"] == 0.0


def test_qeval_precision_recall():
    pr = qeval_mod.precision_recall({"a", "b"}, {"b", "c"})
    assert pr == {"precision": 0.5, "recall": 0.5}
    assert qeval_mod.precision_recall(set(), {"b"})["recall"] == 0.0


def test_oracle_selection_set():
    ledger = _ledger()
    got = exp_mod.oracle_selection_set(
        ledger, "event-store backend", "2025-06-30")
    assert "adr-007" in got
    assert "session-033" not in got  # preference, not evidence


def test_probe_tasks_fixed():
    tasks = exp_mod.probe_tasks()
    assert [t.task_id for t in tasks] == [
        "eq-ol-01", "eq-ol-02", "eq-rv-01", "eq-cx-01"]
    assert all(t.as_of == "2025-06-30" for t in tasks)


def test_overload_dump_superset():
    data = run_mod.build_inputs()
    world, tasks, views = (data["world"], data["tasks"], data["views"])
    task = next(t for t in exp_mod.probe_tasks()
                if t.task_id == "eq-ol-01")
    tv = [v for v in views if v["date"] <= task.as_of]
    pool = exp_mod.overload_views(task, tv, world)
    assert len(pool) > 5


def test_revocation_conflict_probes_present():
    data = run_mod.build_inputs()
    world, tasks, views = (data["world"], data["tasks"], data["views"])
    ptasks = {t.task_id: t for t in exp_mod.probe_tasks()}
    tv = [v for v in views if v["date"] <= "2025-06-30"]
    pool, meta = exp_mod.revocation_probe(ptasks["eq-rv-01"], tv, world)
    assert pool is not None and meta.get("revoked")
    pool, note = exp_mod.conflict_views(ptasks["eq-cx-01"], tv, world)
    assert pool is not None and len(pool) == 2


def test_policy_version_frozen():
    assert pipe_mod.POLICY_VERSION == "project-memory-v1"


def test_expansion_dry_run_builds_all_rows():
    data = run_mod.build_inputs()
    world, tasks, views = (data["world"], data["tasks"], data["views"])
    ledger = data["ledger"]
    rows = []
    for task in tasks:
        for cond, context in exprun_mod.action_contexts(
                task, views, world).items():
            rows.append(exprun_mod._target_row(
                None, "dry", task, world, cond, context, "m",
                dry_run=True))
    assert len(rows) == 11 * 5
    for qtask in exp_mod.all_qtasks(ledger):
        rows.extend(exprun_mod.q_rows(
            qtask, views, world, None, "dry", "m", dry_run=True))
    for ptask in exp_mod.probe_tasks():
        rows.extend(exprun_mod.probe_rows(
            ptask, views, world, None, "dry", "m", dry_run=True))
    conds = {r["condition"] for r in rows}
    assert {"E0", "E1", "E2", "EA", "EO", "QE0", "QE1", "QE2", "EO",
            "OL", "RV", "CX"} <= conds
