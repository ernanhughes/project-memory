"""Simulator mechanics tests: world state, tasks, scoring, overlays.

Every behavioural number asserted here is derived, not guessed: oracle
perfection and null failure follow from the scorer by construction;
discrimination counts (lexical vs oracle, overlays) were observed on
the frozen seed first and are pinned as regression values with the
mechanism named beside each pin.
"""

from generator import build
from generator.schema import LedgerError, Record

from simulator import actors as actor_mod
from simulator import overlays as overlays_mod
from simulator import run as run_mod
from simulator import scores as scores_mod
from simulator import tasks as tasks_mod
from simulator.world import WorldState

SEED = 20240823


def _inputs(n_worlds=12):
    return run_mod.build_inputs(seed=SEED, n_worlds=n_worlds)


def test_task_cut_has_current_targets():
    data = _inputs()
    assert len(data["tasks"]) >= 10
    for task in data["tasks"]:
        assert data["world"].current_target(task.topic)


def test_rejection_topics_yield_no_task():
    data = _inputs()
    world = data["world"]
    redis = [t for t in data["tasks"] if t.topic == "lookup-latency caching"]
    assert redis == []
    assert world.current_target("lookup-latency caching") is None


def test_actor_views_carry_no_ledger():
    data = _inputs()
    for view in data["views"]:
        assert set(view) == {"display_id", "kind", "date", "title",
                             "body"}
    assert all(v["date"] <= tasks_mod.TASK_CUT for v in data["views"])


def test_oracle_perfect_null_zero():
    data = _inputs()
    world, tasks, views = data["world"], data["tasks"], data["views"]
    oracle = actor_mod.OracleActor(world)
    null = actor_mod.NullActor()
    for task in tasks:
        task_views = [v for v in views if v["date"] <= task.as_of]
        assert scores_mod.score_action(
            world, task, oracle.act(task_views, task))["task_score"] == 1.0
        assert scores_mod.score_action(
            world, task, null.act(task_views, task))["task_score"] == 0.0


def test_superseded_actor_harmful_where_options_exist():
    data = _inputs()
    world, tasks, views = data["world"], data["tasks"], data["views"]
    probe = actor_mod.SupersededActor(world)
    harmed = 0
    for task in tasks:
        task_views = [v for v in views if v["date"] <= task.as_of]
        scored = scores_mod.score_action(
            world, task, probe.act(task_views, task))
        assert scored["task_score"] == 0.0
        harmed += scored["harmful"]
        if scored["harmful"]:
            assert scored["codes"] == ("harm.superseded",)
    # World A event-store plus parametric split topics carry superseded
    # options; the probe must bite somewhere to be a probe.
    assert harmed >= 1


def test_lexical_differs_from_oracle_somewhere():
    data = _inputs()
    world, tasks, views = data["world"], data["tasks"], data["views"]
    lexical = actor_mod.LexicalActor()
    oracle = actor_mod.OracleActor(world)
    diffs = 0
    for task in tasks:
        task_views = [v for v in views if v["date"] <= task.as_of]
        mine = scores_mod.score_action(
            world, task, lexical.act(task_views, task))["task_score"]
        want = scores_mod.score_action(
            world, task, oracle.act(task_views, task))["task_score"]
        diffs += mine != want
    assert diffs >= 1


def test_every_scored_action_carries_codes():
    data = _inputs()
    world, tasks, views = data["world"], data["tasks"], data["views"]
    lexical = actor_mod.LexicalActor()
    for task in tasks[:3]:
        task_views = [v for v in views if v["date"] <= task.as_of]
        scored = scores_mod.score_action(
            world, task, lexical.act(task_views, task))
        assert scored["codes"] and all(
            "." in code for code in scored["codes"])


def test_remove_current_decision_degrades_oracle():
    built = build.build_corpus(seed=SEED, n_worlds=12)
    overlay = overlays_mod.remove_record(built["ledger"], "evt-205")
    world = WorldState(overlay, tasks_mod.TASK_CUT)
    assert world.current_target("event-store backend") is None
    oracle = actor_mod.OracleActor(world)
    task = next(t for t in tasks_mod.build_tasks(
        WorldState(built["ledger"], tasks_mod.TASK_CUT), ["event-store backend"]))
    assert scores_mod.score_action(
        world, task,
        oracle.act([], task))["task_score"] == 0.0


def test_invalid_kind_rejected_on_add():
    built = build.build_corpus(seed=SEED, n_worlds=12)
    import pytest
    with pytest.raises(LedgerError):
        overlays_mod.add_record(built["ledger"], Record(
            key="poison-1", kind="hunch", topic="event-store backend",
            content="Use SQLite.", date="2024-07-18",
            scenario="poison_probe"))


def test_stale_decision_harms_lexical_actor():
    built = build.build_corpus(seed=SEED, n_worlds=12)
    from generator.schema import Record as Rec
    poison = Rec(key="poison-1", kind="evidence",
                 topic="event-store backend",
                 content=("Retrospective suggests: Use SQLite for the "
                          "event store going forward."),
                 date="2024-07-18", display_id="session-501",
                 artifact_kind="session", scenario="poison_probe")
    overlay = overlays_mod.add_record(built["ledger"], poison)
    assert overlay.by_key()["poison-1"].content.startswith("Retrospective")
    assert "session-501" not in [r.display_id for r in built["ledger"].records]
    rebuilt = build.build_corpus(seed=SEED, n_worlds=12, ledger=overlay)
    bodies = {a.display_id: a.body for a in rebuilt["artifacts"]}
    assert "session-501" in bodies  # visible to retrieval by construction
    assert "Use SQLite for the event store" in bodies["session-501"]
    world = WorldState(overlay, tasks_mod.TASK_CUT)
    task = next(t for t in tasks_mod.build_tasks(world, ["event-store backend"]))
    views = [actor_mod.artifact_view(a) for a in rebuilt["artifacts"]
             if a.display_id and a.date <= task.as_of]
    lexical = actor_mod.LexicalActor()
    action = lexical.act(views, task)
    scored = scores_mod.score_action(world, task, action)
    # Organic stale-memory influence: the top-ranked stale decision
    # (not the poison, which this query does not surface) drives harm.
    assert action["cited"] == "adr-003"
    assert scored["harmful"] == 1
    assert scored["codes"] == ("harm.superseded",)


def test_frozen_ladder_reproduces_pinned_summary(tmp_path):
    from simulator import run as run_mod
    from generator import manifest as manifest_mod
    out = run_mod.freeze(seed=SEED, n_worlds=12, out=tmp_path / "sim",
                         repo_root=".")
    assert manifest_mod.verify_manifest(out) == []
    import json
    summary = json.loads((out / "results.json").read_text(
        encoding="utf-8"))["summary"]
    # Regression pins from the first frozen run: oracle perfect and
    # harmless, null silent, lexical useful-but-harmful, intervention
    # probes at zero success. Mechanism beside each pin in comments.
    assert summary["oracle"] == {"n": 11, "task_success": 1.0,
                                 "harmful_tasks": 0}
    assert summary["null"] == {"n": 11, "task_success": 0.0,
                               "harmful_tasks": 0}
    assert summary["lexical"]["task_success"] == 0.7273
    assert summary["lexical"]["harmful_tasks"] == 3  # stale SQLite wins
    assert summary["superseded"]["harmful_tasks"] == 3
    assert summary["preference"]["task_success"] == 0.0
