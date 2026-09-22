"""Minimal end-to-end demonstration of the instrument.

History (event-store running example, artifact IDs shared with the book):

    March:    SQLite selected for the event store.
    June:     Concurrent-write failures observed under load.
    July:     PostgreSQL selected (adr-007), superseding SQLite.
    October:  A new service needs an event store.

Five tasks exercise locate, decision, provenance, and temporal scoring.
Four canned systems show how different failure modes produce different
scores. No model inference is required: the point is to test the scorer
plumbing, not any particular memory system.

Run from ``experiments/benchmark``::

    python -m memory_measurement.demo
"""

from __future__ import annotations

from .controls import memory_delta
from .manifests import RunManifest
from .observations import MemoryObservation
from .reports import render_scorecard
from .scorers import score_task
from .tasks import (
    DECISION,
    LOCATE,
    PROVENANCE,
    TEMPORAL,
    UNANSWERABLE,
    HistoryItem,
    MemoryTask,
    SystemOutput,
)

HISTORY: tuple[HistoryItem, ...] = (
    HistoryItem(
        item_id="session-014",
        text="March: team discusses event-store options; SQLite selected "
        "for the first prototype (evt-201).",
        kind="session",
        timestamp="2024-03-04",
    ),
    HistoryItem(
        item_id="evt-202",
        text="June: contention experiment shows SQLite slowing under "
        "concurrent writes.",
        kind="experiment",
        timestamp="2024-06-18",
    ),
    HistoryItem(
        item_id="evt-203",
        text="June: incident report on write contention in the SQLite prototype.",
        kind="incident",
        timestamp="2024-06-25",
    ),
    HistoryItem(
        item_id="adr-007",
        text="July: decision evt-205 — new event-store work should target "
        "PostgreSQL, superseding the earlier SQLite decision (evt-201).",
        kind="decision-record",
        timestamp="2024-07-11",
    ),
)

HISTORY_IDS = tuple(item.item_id for item in HISTORY)

TASKS: tuple[MemoryTask, ...] = (
    MemoryTask(
        task_id="demo-A",
        family=LOCATE,
        prompt="Where was the event-store decision discussed?",
        history_ref="demo-v0.1",
        expected_sources=("session-014", "adr-007"),
    ),
    MemoryTask(
        task_id="demo-B",
        family=DECISION,
        prompt="What event store should new services use?",
        history_ref="demo-v0.1",
        expected_sources=("adr-007",),
        expected_state="PostgreSQL",
        superseded_options=("SQLite",),
    ),
    MemoryTask(
        task_id="demo-C",
        family=PROVENANCE,
        prompt="Why was PostgreSQL chosen?",
        history_ref="demo-v0.1",
        expected_sources=("evt-202", "evt-203", "adr-007"),
        expected_state="concurrent-write contention",
    ),
    MemoryTask(
        task_id="demo-D",
        family=TEMPORAL,
        prompt="What event store did the March prototype use?",
        history_ref="demo-v0.1",
        expected_sources=("session-014",),
        temporal_mode="historical",
        expected_current="PostgreSQL",
        expected_historical="SQLite",
    ),
    MemoryTask(
        task_id="demo-E",
        family=TEMPORAL,
        prompt="What event store should new code target today?",
        history_ref="demo-v0.1",
        expected_sources=("adr-007",),
        temporal_mode="current",
        expected_current="PostgreSQL",
        expected_historical="SQLite",
        superseded_options=("SQLite",),
    ),
    MemoryTask(
        task_id="demo-F",
        family=DECISION,
        prompt="What cache layer was adopted for the event store?",
        history_ref="demo-v0.1",
        expected_sources=(),
        expected_status=UNANSWERABLE,
        notes="No cache decision exists in this history; abstention is correct.",
    ),
)

# Four canned systems: each maps task_id -> SystemOutput.
GOOD: dict[str, SystemOutput] = {
    "demo-A": SystemOutput(
        task_id="demo-A", retrieved_ids=("session-014", "adr-007"),
        answer="Discussed in session-014; decided in adr-007.",
        cited_sources=("session-014", "adr-007"),
    ),
    "demo-B": SystemOutput(
        task_id="demo-B", retrieved_ids=("adr-007",),
        answer="New services should use PostgreSQL per adr-007.",
        cited_sources=("adr-007",),
    ),
    "demo-C": SystemOutput(
        task_id="demo-C", retrieved_ids=("evt-202", "evt-203", "adr-007"),
        answer="PostgreSQL was chosen because the contention experiment "
        "(evt-202) and the write-contention incident (evt-203) demonstrated "
        "concurrent-write contention in the SQLite prototype.",
        cited_sources=("evt-202", "evt-203", "adr-007"),
    ),
    "demo-D": SystemOutput(
        task_id="demo-D", retrieved_ids=("session-014",),
        answer="The March prototype used SQLite.",
        cited_sources=("session-014",),
    ),
    "demo-E": SystemOutput(
        task_id="demo-E", retrieved_ids=("adr-007",),
        answer="New code should target PostgreSQL.",
        cited_sources=("adr-007",),
    ),
    "demo-F": SystemOutput(task_id="demo-F", abstained=True),
}

STALE: dict[str, SystemOutput] = {
    "demo-A": SystemOutput(
        task_id="demo-A", retrieved_ids=("session-014",),
        answer="Discussed in session-014.", cited_sources=("session-014",),
    ),
    "demo-B": SystemOutput(
        task_id="demo-B", retrieved_ids=("session-014",),
        answer="Use SQLite, as decided in March.",
        cited_sources=("session-014",),
    ),
    "demo-C": SystemOutput(
        task_id="demo-C", retrieved_ids=("session-014",),
        answer="SQLite was chosen for simplicity.",
        cited_sources=("session-014",),
    ),
    "demo-D": SystemOutput(
        task_id="demo-D", retrieved_ids=("session-014",),
        answer="The March prototype used SQLite.",
        cited_sources=("session-014",),
    ),
    "demo-E": SystemOutput(
        task_id="demo-E", retrieved_ids=("session-014",),
        answer="Use SQLite.", cited_sources=("session-014",),
    ),
    "demo-F": SystemOutput(
        task_id="demo-F", answer="Redis was adopted.",
        cited_sources=("session-099",),
    ),
}

FLUENT_WRONG: dict[str, SystemOutput] = {
    "demo-A": SystemOutput(
        task_id="demo-A",
        retrieved_ids=("session-014", "evt-202", "evt-203"),
        answer="The decision was discussed across March and June sessions.",
        cited_sources=("session-014", "benchmark-126"),
    ),
    "demo-B": SystemOutput(
        task_id="demo-B", retrieved_ids=("evt-202",),
        answer="The team moved to PostgreSQL because of benchmark-126.",
        cited_sources=("benchmark-126",),
    ),
    "demo-C": SystemOutput(
        task_id="demo-C", retrieved_ids=("evt-202",),
        answer="Contention was observed.", cited_sources=("evt-202",),
    ),
    "demo-D": SystemOutput(
        task_id="demo-D", retrieved_ids=("session-014",),
        answer="PostgreSQL has always been the choice.",
        cited_sources=("session-014",),
    ),
    "demo-E": SystemOutput(
        task_id="demo-E", retrieved_ids=("session-014",),
        answer="PostgreSQL.", cited_sources=("session-014",),
    ),
    "demo-F": SystemOutput(
        task_id="demo-F", answer="No cache was adopted.",
        cited_sources=("adr-007",),
    ),
}


def run_system(
    name: str, outputs: dict[str, SystemOutput]
) -> tuple[list[MemoryObservation], RunManifest]:
    manifest = RunManifest(
        run_id=f"demo-{name}",
        system_name=name,
        condition="canned-demo",
        corpus_version="demo-v0.1",
        task_set_version="demo-tasks-v0.1",
        notes="Canned outputs; scorer plumbing demonstration only.",
    )
    observations: list[MemoryObservation] = []
    for task in TASKS:
        observations.extend(
            score_task(task, outputs[task.task_id], HISTORY_IDS)
        )
    return observations, manifest


def main() -> None:
    systems = {
        "good-memory": GOOD,
        "stale-memory": STALE,
        "fluent-wrong": FLUENT_WRONG,
    }
    means: dict[str, float] = {}
    for name, outputs in systems.items():
        observations, manifest = run_system(name, outputs)
        print(render_scorecard(observations, manifest))
        decisions = [
            o.value for o in observations if o.metric == "decision_exactness"
        ]
        means[name] = sum(1.0 if v else 0.0 for v in decisions) / len(decisions)
    print("Memory delta (decision_exactness vs stale-memory)")
    for name in ("good-memory", "fluent-wrong"):
        print(f"  {name}: {memory_delta(means[name], means['stale-memory']):+.2f}")


if __name__ == "__main__":
    main()
