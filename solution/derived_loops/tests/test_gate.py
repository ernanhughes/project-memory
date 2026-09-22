from derived_loops import fixtures as fx
from derived_loops.baselines import run_condition
from derived_loops.experiments import run_suite
from derived_loops.gate import check_candidate
from derived_loops.metrics import score_task


def test_genuine_passes_staged_gate():
    task = next(t for t in fx.all_tasks() if t.task_id == "t-full-scope")
    by_id = {d.candidate_id: d for d in run_condition("staged", task)}
    assert by_id["c-docs-flags"].admitted
    assert by_id["c-cli-half"].admitted
    assert by_id["c-web"].admitted


def test_traps_rejected_with_stage():
    task = next(t for t in fx.all_tasks() if t.task_id == "t-full-scope")
    by_id = {d.candidate_id: d for d in run_condition("staged", task)}
    assert not by_id["c-facade-delete"].admitted
    assert by_id["c-facade-delete"].stage_failed == "S4"
    assert not by_id["c-tests-remove"].admitted
    assert not by_id["c-docs-deferral"].admitted


def test_stale_leg_rejected():
    task = next(t for t in fx.all_tasks() if t.task_id == "t-stale-leg")
    by_id = {d.candidate_id: d for d in run_condition("staged", task)}
    assert by_id["c-backup-stale"].stage_failed == "S3"


def test_inferred_expected_rejected():
    task = next(t for t in fx.all_tasks() if t.task_id == "t-guess")
    by_id = {d.candidate_id: d for d in run_condition("staged", task)}
    assert by_id["c-guess"].stage_failed == "S2"


def test_trap_only_abstention():
    task = next(t for t in fx.all_tasks() if t.task_id == "t-trap-only")
    score = score_task(task, run_condition("staged", task))
    assert score["abstention_ok"]


def test_unconstrained_is_harmful():
    task = next(t for t in fx.all_tasks() if t.task_id == "t-full-scope")
    score = score_task(task, run_condition("unconstrained", task))
    assert score["harmful_listed"] == ["c-facade-delete"]
    assert score["inferred_precision"] < 1.0


def test_abstain_control_zero_recall():
    suite_tasks = fx.all_tasks()
    for task in suite_tasks:
        score = score_task(task, run_condition("abstain", task))
        assert score["admitted"] == []
        assert score["harmful_listed"] == []


def test_backtest_rejects_loosening():
    suite = run_suite()
    assert suite["backtest"]["promoted"] is False
    assert suite["backtest"]["breaches"]


def test_no_explicit_leak():
    for task in fx.all_tasks():
        score = score_task(task, run_condition("staged", task))
        assert score["explicit_leak"] == []


def test_deterministic_replay():
    first = run_suite()
    second = run_suite()
    assert first == second


def test_zero_denominator_is_null_not_zero():
    task = next(t for t in fx.all_tasks() if t.task_id == "t-trap-only")
    staged = score_task(task, run_condition("staged", task))
    assert staged["inferred_precision"] is None
    assert staged["inferred_recall"] is None
    assert staged["abstention_ok"]
    suite = run_suite()
    assert suite["conditions"]["staged"]["aggregate"][
        "mean_inferred_precision"] == 1.0
    assert suite["conditions"]["staged"]["aggregate"][
        "mean_inferred_recall"] == 1.0
    assert suite["conditions"]["staged"]["aggregate"][
        "micro_precision"] == 1.0
    assert suite["conditions"]["staged"]["aggregate"][
        "micro_recall"] == 1.0
