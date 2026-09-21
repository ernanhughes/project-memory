"""Held-out generalization expansion: Q-tasks and probes (capstone).

Q1/Q2 reuse frozen v0.1 queries/expected (repurposed as id-seeking
tasks with derived decision/production artifact answers). Q3/Q4/Q5,
recall-goal, overload, revocation, conflict, and irrelevant tasks
are built here deterministically from the ledger; expected answers
are ledger-derived, never guessed. Q6 selection is deterministic
(no reader): admitted set vs oracle set precision/recall.

Task ids are namespaced eq-*/aq-* (expansion) to avoid collision
with the 11-task action family (task-*). Nothing here edits frozen
fixtures, tasks, or runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "experiments" \
    / "benchmark" / "fixtures" / "v0.1"


@dataclass(frozen=True)
class QTask:
    task_id: str
    family: str  # Q1 | Q2 | Q3 | Q4 | Q5 | Q-recall | Q-irr
    topic: str
    text: str
    as_of: str
    query_kind: str  # ids | yesno | echo
    expected_ids: tuple = ()
    expected_bool: bool | None = None
    expected_string: str = ""
    project: str = "main"


def _load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def frozen_queries() -> list[dict]:
    return _load_jsonl(FIXTURES / "corpus" / "queries.jsonl")


def frozen_expected() -> dict:
    return {e["query_id"]: e for e in _load_jsonl(
        FIXTURES / "eval" / "expected.jsonl")}


# Q1/Q2 picks (deterministic rule): first three Q1 / first two
# Q2-decision / first one Q2-production by query id with non-empty
# supporting sets, spanning World A and parametric worlds.
Q1_IDS = ("q-000008", "q-000018", "q-000024")
Q2_IDS = ("q-000009", "q-000006", "q-000010")


def q1q2_tasks() -> list[QTask]:
    queries = {q["query_id"]: q for q in frozen_queries()}
    expected = frozen_expected()
    tasks = []
    for qid in Q1_IDS + Q2_IDS:
        query = queries[qid]
        exp = expected[qid]
        assert exp["supporting"], qid
        tasks.append(QTask(
            task_id=f"eq-{qid}",
            family="Q1" if query["family"] == "Q1" else "Q2",
            topic=query["topic"], text=query["text"],
            as_of=query["as_of"], query_kind="ids",
            expected_ids=tuple(sorted(exp["supporting"]))))
    return tasks


def q3_tasks(ledger) -> list[QTask]:
    """Why-tasks: list evidence ids supporting the decision."""
    out = []
    seen = 0
    for topic in sorted({r.topic for r in ledger.records}):
        decs = [r for r in ledger.records
                if r.topic == topic and r.kind == "decision"
                and r.supported_by]
        if not decs:
            continue
        dec = max(decs, key=lambda r: (r.date, r.key))
        by_key = {r.key: r for r in ledger.records}
        support = sorted(
            {by_key[k].display_id for k in dec.supported_by
             if k in by_key and by_key[k].display_id})
        if not support or seen >= 2:
            continue
        seen += 1
        out.append(QTask(
            task_id=f"eq-q3-{seen:02d}", family="Q3", topic=topic,
            text=(f"Which evidence supports the {topic} decision "
                  f"({dec.display_id})?"),
            as_of="2025-06-30", query_kind="ids",
            expected_ids=tuple(support)))
    assert len(out) == 2
    return out


def q4_tasks() -> list[QTask]:
    """Still-true binary tasks with ledger-derived answers."""
    return [
        QTask(task_id="eq-q4-01", family="Q4",
              topic="production event-store backend",
              text=("Is PostgreSQL the current production event-store "
                    "backend as of 2025-06-30?"),
              as_of="2025-06-30", query_kind="yesno",
              expected_bool=True),
        QTask(task_id="eq-q4-02", family="Q4",
              topic="production event-store backend",
              text=("Is SQLite the current production event-store "
                    "backend as of 2025-06-30?"),
              as_of="2025-06-30", query_kind="yesno",
              expected_bool=False),
    ]


def q5_tasks() -> list[QTask]:
    """Unfinished-work tasks at two cuts with different open sets."""
    return [
        QTask(task_id="eq-q5-01", family="Q5", topic="release obligations",
              text=("What migration follow-up work is still open as of "
                    "2024-08-23?"),
              as_of="2024-08-23", query_kind="ids",
              expected_ids=("fixture-scan-109", "session-051")),
        QTask(task_id="eq-q5-02", family="Q5", topic="release obligations",
              text=("What migration follow-up work is still open as of "
                    "2024-07-20?"),
              as_of="2024-07-20", query_kind="ids",
              expected_ids=("session-051",)),
    ]


def recall_task() -> QTask:
    return QTask(
        task_id="eq-recall-01", family="Q-recall",
        topic="event-store backend",
        text=("List the session ids recording the event-store "
              "decision evidence (proposal, preference, benchmark, "
              "contention)."),
        as_of="2025-06-30", query_kind="ids",
        expected_ids=("session-014", "session-019", "session-031",
                      "session-033"))


def irrelevant_task() -> QTask:
    return QTask(
        task_id="eq-irr-01", family="Q-irr", topic="release identifier",
        text=("Repeat the release identifier R-24-083 exactly."),
        as_of="2025-06-30", query_kind="echo",
        expected_string="R-24-083")


def all_qtasks(ledger) -> list[QTask]:
    return (q1q2_tasks() + q3_tasks(ledger) + q4_tasks() + q5_tasks()
            + [recall_task(), irrelevant_task()])


def oracle_selection_set(ledger, topic: str, as_of: str) -> set[str]:
    """Independent oracle for Q6 selection scoring: decision plus
    support plus evidence display ids on topic at cut."""
    out = set()
    for record in ledger.records:
        if record.topic != topic or record.date > as_of:
            continue
        if record.kind in ("decision", "evidence"):
            if record.display_id:
                out.add(record.display_id)
            if record.second_display_id:
                out.add(record.second_display_id)
    return out


# -- Action-flow probes (overload / revocation / conflict) ---------------

def overload_views(task, views: list[dict], world) -> list[dict]:
    """Maximal topical dump: every ledger-backed same-topic artifact
    (any kind, any validity) plus untagged context artifacts. The
    unfiltered extreme E2 must beat (or tie) without ever seeing."""
    topics = {task.topic, None}
    return [v for v in views if _view_topic(v, world) in topics]


def _view_topic(view: dict, world) -> str | None:
    for record in world.ledger.records:
        if (record.display_id == view["display_id"]
                or record.second_display_id == view["display_id"]):
            return record.topic
    return None


def revocation_probe(task, views: list[dict], world):
    """Decision plus designated-revoked supporting evidence.

    Returns (pool_views, revoked_display_id) or (None, reason).
    Only topics with supporting evidence qualify (event-store in
    v0.1 scope); the designation is probe metadata, the ledger is
    untouched, and content renders normally (invisibility by
    design).
    """
    from simulator import wrong_memory as wm_mod
    cur = wm_mod.current_decision(world, task.topic, task.as_of)
    target = None
    if cur is not None:
        for key in cur.supported_by:
            rec = world.ledger.by_key().get(key)
            if rec is not None and rec.kind == "evidence":
                target = rec
                break
    if cur is None or target is None:
        return None, "no-supporting-evidence"
    by_display = {v["display_id"]: v for v in views}
    pool = [v for did, v in ((cur.display_id, None),
                             (target.display_id, None))
            if did in by_display for v in [by_display[did]]]
    return pool, {"revoked": [target.display_id]}


def conflict_views(task, views: list[dict], world):
    """Current decision plus contradicting losing preference.

    Fully ledger-grounded (no construction): the preference
    contradicts by content while the decision authorizes. Returns
    (pool, note); empty pool with reason where the pair is absent.
    """
    dec = None
    for record in world.ledger.records:
        if (record.topic == task.topic and record.kind == "decision"
                and record.date <= task.as_of):
            dec = record
    prefs = [r for r in world.ledger.records
             if r.topic == task.topic and r.kind == "preference"
             and r.date <= task.as_of]
    if dec is None or not prefs or not dec.display_id:
        return None, "no-decision-preference-pair"
    by_display = {v["display_id"]: v for v in views}
    want = [dec.display_id] + [prefs[0].display_id]
    pool = [by_display[d] for d in want if d in by_display]
    if len(pool) < 2:
        return None, "pair-incomplete-in-views"
    return pool, "decision-vs-preference"


def probe_tasks() -> list:
    """Action-flow probe tasks (TARGET scoring) with fixed ids.

    eq-ol-01/02 overload (maximal topical dump); eq-rv-01 revocation
    (designated revoked evidence beside the live decision); eq-cx-01
    conflict (decision plus contradicting preference). Same action
    query shape as the new-service family; as_of 2025-06-30.
    """
    from simulator.tasks import TaskPacket
    base = "Propose the implementation target."
    return [
        TaskPacket(task_id="eq-ol-01", family="action-probe",
                   topic="message-queue backend", text=(
                       "Add a new service that needs message-queue "
                       "backend. " + base),
                   as_of="2025-06-30"),
        TaskPacket(task_id="eq-ol-02", family="action-probe",
                   topic="session cache", text=(
                       "Add a new service that needs session cache. "
                       + base),
                   as_of="2025-06-30"),
        TaskPacket(task_id="eq-rv-01", family="action-probe",
                   topic="event-store backend", text=(
                       "Add a new service that needs event-store "
                       "backend. " + base),
                   as_of="2025-06-30"),
        TaskPacket(task_id="eq-cx-01", family="action-probe",
                   topic="event-store backend", text=(
                       "Add a new service that needs event-store "
                       "backend. " + base),
                   as_of="2025-06-30"),
    ]
