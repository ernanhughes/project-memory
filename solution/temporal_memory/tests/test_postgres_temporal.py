"""PostgreSQL adapter tests for the temporal event model.

Skipped gracefully without PostgreSQL so the unit suite stays green::

    $env:MEMORY_BASELINE_DSN = "postgresql://postgres:<pw>@localhost:5432/memory_baseline"
    python -m pytest temporal_memory/tests/test_postgres_temporal.py -v
"""

from __future__ import annotations

import os

import pytest

psycopg = pytest.importorskip("psycopg")

from temporal_memory import fixtures as fx  # noqa: E402
from temporal_memory import postgres as pg  # noqa: E402
from temporal_memory.health import health_report  # noqa: E402
from temporal_memory.log import EventLog  # noqa: E402
from temporal_memory.model import REDUCER_VERSION, SCHEMA_VERSION  # noqa: E402
from temporal_memory.query import TemporalEngine  # noqa: E402
from temporal_memory.reducer import projection_digest, replay  # noqa: E402
from temporal_memory.ordering import temporal_sort  # noqa: E402

DSN = os.environ.get(
    "MEMORY_BASELINE_DSN",
    "postgresql://postgres:postgres@localhost:5434/memory_baseline",
)
SCHEMA = "temporal_pg_it"


def available() -> bool:
    try:
        psycopg.connect(DSN, connect_timeout=3).close()
    except Exception:
        return False
    return True


needs_pg = pytest.mark.skipif(not available(), reason="PostgreSQL unavailable")


def connect():
    return psycopg.connect(DSN, autocommit=True)


def reset():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
            cur.execute(f'CREATE SCHEMA "{SCHEMA}"')
    finally:
        conn.close()


@needs_pg
def test_initialise_is_idempotent() -> None:
    reset()
    conn = connect()
    try:
        first = pg.initialise(conn, SCHEMA)
        second = pg.initialise(conn, SCHEMA)
        assert first == second
        assert first["event_schema_version"] == SCHEMA_VERSION
        assert first["reducer_version"] == REDUCER_VERSION
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)",
                        (f"{SCHEMA}.temporal_events",))
            assert cur.fetchone()[0] is not None
    finally:
        conn.close()


@needs_pg
def test_append_load_round_trip_with_digest_equivalence() -> None:
    reset()
    events = fx.canonical_migration()
    conn = connect()
    try:
        pg.initialise(conn, SCHEMA)
        for event in events:
            out = pg.append_event(conn, SCHEMA, event,
                                  "2026-09-20T00:00:00Z")
            assert out["appended"] is True
        assert pg.event_count(conn, SCHEMA) == len(events)
        loaded = pg.load_log(conn, SCHEMA)
        mem = EventLog()
        for event in events:
            mem.append(event, "2026-09-20T00:00:00Z")
        assert loaded.digest() == mem.digest()
        d_loaded = projection_digest(replay(temporal_sort(
            loaded.events(), loaded.by_id())))
        d_mem = projection_digest(replay(temporal_sort(
            mem.events(), mem.by_id())))
        assert d_loaded == d_mem
        # relations + axes survive the round trip
        by_id = loaded.by_id()
        decision = by_id["ch8-decision"]
        assert decision.causal_parents == ("ch8-benchmark", "ch8-contention")
        assert decision.effective_from == "2026-07-10T09:00:00Z"
        assert "PostgreSQL" in decision.value
        assert TemporalEngine(loaded).current(
            fx.SUBJECT_BACKEND).value == "PostgreSQL"
    finally:
        conn.close()


@needs_pg
def test_duplicate_replay_is_idempotent_conflict_fails() -> None:
    reset()
    event = fx.canonical_migration()[0]
    conn = connect()
    try:
        pg.initialise(conn, SCHEMA)
        stamp = "2026-09-20T00:00:00Z"
        assert pg.append_event(conn, SCHEMA, event, stamp)["appended"] is True
        replay = pg.append_event(conn, SCHEMA, event, stamp)
        assert replay == {"appended": False, "duplicate": True,
                          "event_id": event.event_id}
        assert pg.event_count(conn, SCHEMA) == 1
        altered = fx.E("ch8-sqlite-current", "ledger", 1, "STATE_CHANGED",
                       fx.SUBJECT_BACKEND, "2026-03-02T09:00:00Z",
                       "2026-03-02T09:05:00Z", value="CHANGED")
        with pytest.raises(ValueError, match="TEMPORAL_DUPLICATE_CONFLICT"):
            pg.append_event(conn, SCHEMA, altered, stamp)
    finally:
        conn.close()


@needs_pg
def test_invalid_event_rejected_with_codes() -> None:
    reset()
    conn = connect()
    try:
        pg.initialise(conn, SCHEMA)
        bad = fx.E("ch8-bad", "s", 0, "NOPE", fx.SUBJECT_BACKEND,
                   "not-a-time", "2026-01-02T00:00:01Z")
        with pytest.raises(ValueError, match="TEMPORAL_EVENT_INVALID"):
            pg.append_event(conn, SCHEMA, bad, "t")
        assert pg.event_count(conn, SCHEMA) == 0
    finally:
        conn.close()


@needs_pg
def test_out_of_order_arrival_replays_deterministically() -> None:
    reset()
    events = fx.canonical_migration()
    conn = connect()
    try:
        pg.initialise(conn, SCHEMA)
        for event in reversed(events):
            pg.append_event(conn, SCHEMA, event, "2026-09-20T00:00:00Z")
        loaded = pg.load_log(conn, SCHEMA)
        assert [e.event_id for e in loaded.events()] == [
            e.event_id for e in reversed(events)]
        assert TemporalEngine(loaded).current(
            fx.SUBJECT_BACKEND).value == "PostgreSQL"
    finally:
        conn.close()


@needs_pg
def test_gap_and_health_visible() -> None:
    reset()
    conn = connect()
    try:
        pg.initialise(conn, SCHEMA)
        for event in fx.gap_stream():
            pg.append_event(conn, SCHEMA, event, "2026-09-20T00:00:00Z")
        loaded = pg.load_log(conn, SCHEMA)
        assert loaded.gaps()
        report = health_report(loaded)
        assert report["sequence_gaps"]
        assert report["events"] == len(fx.gap_stream())
        assert pg.subjects(conn, SCHEMA)
        versions = pg.versions(conn, SCHEMA)
        assert versions["reducer_version"] == REDUCER_VERSION
    finally:
        conn.close()
