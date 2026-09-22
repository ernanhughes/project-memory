"""Deterministic fixtures for the E9 suite.

Timeline anchors reuse the book's frozen running-example IDs already
present in Chapter 9's prose (adr-007, commit-112, commit-117,
commit-118, session-040, session-044, session-051, intent-401,
issue-041, release-024). New temporal event IDs live under the ch9-
namespace (solution fixture IDs); non-ledger source identities
(todo-comment, checklist, decisions) are fixture channels, not ledger
artifacts. Dates are 2024, matching the ledger's July/August window.
"""

from __future__ import annotations

from temporal_memory.log import EventLog
from temporal_memory.model import EventEnvelope

from .model import ExpectedTransition, Expectation

SUBJECT_BACKUP = "backup.backend"
SUBJECT_DOCS = "docs.storage_backend"
SUBJECT_FIXTURES = "benchmark.fixtures_db"
SUBJECT_TUNING = "perf.tuning"
SUBJECT_STORE = "event-store.backend"
SUBJECT_FLAG = "feature-x.enabled"
SUBJECT_TOKEN = "auth.token_rotated"

STMT_BACKUP = "Move backups to PostgreSQL before release."
STMT_DOCS = "Update deployment docs to PostgreSQL before release."
STMT_DOCS_SEM = "Update deployment docs to PostgreSQL."
STMT_TUNE = "Tune SQLite write performance."
STMT_STAGING = "Migrate staging backups before release."
STMT_FLAG = "Disable the feature flag after the incident."
STMT_TOKEN = "Rotate the service token before 30 September."


def E(event_id: str, source_id: str, source_seq: int, event_type: str,
      subject: str, event_time: str, recorded_at: str, value: str = "",
      state_key: str = "", effective_from: str | None = None,
      payload: tuple[tuple[str, str], ...] = (),
      evidence_refs: tuple[str, ...] = (),
      causal_parents: tuple[str, ...] = ()) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id, source_id=source_id, source_seq=source_seq,
        event_type=event_type, subject=subject, state_key=state_key,
        value=value, event_time=event_time, recorded_at=recorded_at,
        effective_from=effective_from, payload=payload,
        evidence_refs=evidence_refs, causal_parents=causal_parents)


def _role(role: str, target: str) -> tuple[tuple[str, str], ...]:
    return (("open_loops.role", role), ("open_loops.target", target))


def X(exp_id: str, subject: str, target: str, opened_at: str,
      evidence: tuple[str, ...], statement: str,
      required_before: str | None = None,
      trigger: str | None = None) -> Expectation:
    return Expectation(
        expectation_id=exp_id, subject=subject,
        desired=ExpectedTransition(subject=subject, predicate="equals",
                                   target=target),
        opened_at=opened_at, opening_evidence=evidence, statement=statement,
        derivation="ledger-established", required_before=required_before,
        trigger=trigger)


def EXP_BACKUP() -> Expectation:
    return X("intent-401", SUBJECT_BACKUP, "PostgreSQL",
             "2024-07-17T10:00:00Z", ("session-051",), STMT_BACKUP,
             required_before="ch9-release")


def EXP_DOCS() -> Expectation:
    return X("exp-docs", SUBJECT_DOCS, "PostgreSQL",
             "2024-07-22T10:00:00Z", ("ch9-docs-open",), STMT_DOCS,
             required_before="ch9-release")


def EXP_DOCS_SEM() -> Expectation:
    return X("exp-docs-sem", SUBJECT_DOCS, "PostgreSQL",
             "2024-07-22T10:00:00Z", ("ch9-docs-open",), STMT_DOCS_SEM)


def EXP_FIXTURES() -> Expectation:
    return X("exp-fixtures", SUBJECT_FIXTURES, "PostgreSQL",
             "2024-07-22T10:00:00Z", ("ch9-docs-open",),
             "Update benchmark fixtures for PostgreSQL.")


def EXP_TUNE() -> Expectation:
    return X("exp-tune", SUBJECT_TUNING, "improved",
             "2024-05-06T10:00:00Z", ("issue-041",), STMT_TUNE)


def EXP_STAGING() -> Expectation:
    return X("exp-staging", "staging.backup", "PostgreSQL",
             "2024-07-18T10:00:00Z", ("session-051",), STMT_STAGING)


def EXP_FLAG() -> Expectation:
    return X("exp-flag", SUBJECT_FLAG, "off",
             "2024-08-02T10:00:00Z", ("ch9-incident",), STMT_FLAG,
             trigger="ch9-incident")


def EXP_TOKEN() -> Expectation:
    return X("exp-token", SUBJECT_TOKEN, "rotated",
             "2024-09-01T10:00:00Z", ("ch9-token-open",), STMT_TOKEN,
             required_before="2024-09-30T00:00:00Z")


def canonical_history() -> tuple[list[EventEnvelope], dict[str, str]]:
    """Full release history: migration context + all Ch9 transitions."""
    events = [
        E("ch9-tune-task", "issue-041", 1, "TASK_CREATED", SUBJECT_TUNING,
          "2024-05-06T10:00:00Z", "2024-05-06T10:05:00Z", value="open"),
        E("ch9-migrate-decision", "decisions", 1, "DECISION_MADE",
          SUBJECT_STORE, "2024-07-11T10:00:00Z", "2024-07-11T10:05:00Z",
          value="PostgreSQL", effective_from="2024-07-22T09:00:00Z",
          payload=_role("supersede", "exp-tune"),
          evidence_refs=("adr-007",)),
        E("ch9-migrate-script", "commit-112", 1, "STATE_CHANGED",
          SUBJECT_STORE, "2024-07-15T10:00:00Z", "2024-07-15T10:05:00Z",
          value="PostgreSQL", effective_from="2024-07-15T10:00:00Z",
          evidence_refs=("commit-112",)),
        E("ch9-backup-remark", "session-051", 1, "OBSERVATION_RECORDED",
          SUBJECT_BACKUP, "2024-07-17T10:00:00Z", "2024-07-17T10:05:00Z",
          evidence_refs=("session-051",)),
        E("ch9-backup-todo", "todo-comment", 1, "OBSERVATION_RECORDED",
          SUBJECT_BACKUP, "2024-07-18T10:00:00Z", "2024-07-18T10:05:00Z"),
        E("ch9-backup-checklist", "checklist", 1, "OBSERVATION_RECORDED",
          SUBJECT_BACKUP, "2024-07-19T10:00:00Z", "2024-07-19T10:05:00Z"),
        E("ch9-redis-remark", "session-040", 1, "OBSERVATION_RECORDED",
          "cache.redis", "2024-06-28T10:00:00Z", "2024-06-28T10:05:00Z",
          evidence_refs=("session-040",)),
        E("ch9-redis-close", "session-044", 1, "OBSERVATION_RECORDED",
          "cache.redis", "2024-07-02T10:00:00Z", "2024-07-02T10:05:00Z",
          evidence_refs=("session-044",)),
        E("ch9-docs-open", "docs-note", 1, "OBSERVATION_RECORDED",
          SUBJECT_DOCS, "2024-07-22T10:00:00Z", "2024-07-22T10:05:00Z"),
        E("ch9-false-cleanup", "commit-119", 1, "OBSERVATION_RECORDED",
          SUBJECT_BACKUP, "2024-08-05T10:00:00Z", "2024-08-05T10:05:00Z"),
        E("ch9-refactor", "commit-120", 1, "STATE_CHANGED",
          SUBJECT_FIXTURES, "2024-08-12T10:00:00Z", "2024-08-12T10:05:00Z",
          value="PostgreSQL", effective_from="2024-08-12T10:00:00Z"),
        E("ch9-docs-commit", "commit-117", 1, "STATE_CHANGED",
          SUBJECT_DOCS, "2024-08-20T10:00:00Z", "2024-08-20T10:05:00Z",
          value="PostgreSQL", effective_from="2024-08-20T10:00:00Z",
          evidence_refs=("commit-117",)),
        E("ch9-scope-decision", "decisions", 2, "DECISION_MADE",
          "staging.backup", "2024-08-21T10:00:00Z", "2024-08-21T10:05:00Z",
          payload=_role("cancel", "exp-staging")),
        E("ch9-backup-migrate", "commit-118", 1, "STATE_CHANGED",
          SUBJECT_BACKUP, "2024-08-27T10:00:00Z", "2024-08-27T10:05:00Z",
          value="PostgreSQL", effective_from="2024-08-27T10:00:00Z",
          evidence_refs=("commit-118",)),
        E("ch9-release", "release-svc", 1, "STATE_CHANGED",
          "release-024", "2024-08-30T10:00:00Z", "2024-08-30T10:05:00Z",
          value="shipped", effective_from="2024-08-30T10:00:00Z",
          evidence_refs=("release-024",)),
    ]
    texts = {
        "ch9-tune-task": "Issue: tune SQLite write performance for importer.",
        "ch9-migrate-decision": "Decision: move the event store to PostgreSQL.",
        "ch9-migrate-script": "Migration script added; application writes now use PostgreSQL.",
        "ch9-backup-remark": "Importer is green on PostgreSQL. Backups still target "
                             "SQLite - need to move those before release.",
        "ch9-backup-todo": "TODO: move backups to postgres before release",
        "ch9-backup-checklist": "Release checklist: backups must target PostgreSQL.",
        "ch9-redis-remark": "We should probably use Redis for the importer cache.",
        "ch9-redis-close": "Redis is unnecessary; the working set fits in memory.",
        "ch9-docs-open": "Deployment documentation still describes SQLite; need docs update.",
        "ch9-false-cleanup": "backup cleanup: removed old scripts",
        "ch9-refactor": "speed up importer test harness",
        "ch9-docs-commit": "refresh deploy docs",
        "ch9-scope-decision": "Decision: staging backups are out of scope for this release.",
        "ch9-backup-migrate": "prepare release storage changes",
        "ch9-release": "Release 024 shipped.",
    }
    return events, texts


def freeze(events: list[EventEnvelope]) -> EventLog:
    log = EventLog()
    for i, event in enumerate(events):
        log.append(event, f"2024-09-20T00:00:{i:02d}Z")
    return log


def opening_histories() -> dict[str, tuple[list[EventEnvelope], dict[str, str], str]]:
    """One opening (E0), four subsequent trajectories (H1-H4)."""
    base = [
        E("ch9-h-open", "session-051", 1, "OBSERVATION_RECORDED",
          SUBJECT_BACKUP, "2024-07-17T10:00:00Z", "2024-07-17T10:05:00Z",
          evidence_refs=("session-051",)),
    ]
    base_texts = {
        "ch9-h-open": "Backups still target SQLite - need to move those before release.",
    }

    def tail(events, texts):
        return base + events, dict(base_texts, **texts)

    h1_events, h1_texts = tail(
        [E("ch9-h1-migrate", "commit-118", 1, "STATE_CHANGED",
           SUBJECT_BACKUP, "2024-08-27T10:00:00Z", "2024-08-27T10:05:00Z",
           value="PostgreSQL", effective_from="2024-08-27T10:00:00Z",
           evidence_refs=("commit-118",)),
         E("ch9-h-release", "release-svc", 1, "STATE_CHANGED",
           "release-024", "2024-08-30T10:00:00Z", "2024-08-30T10:05:00Z",
           value="shipped", evidence_refs=("release-024",))],
        {"ch9-h1-migrate": "prepare release storage changes",
         "ch9-h-release": "Release 024 shipped."})
    h2_events, h2_texts = tail(
        [E("ch9-h2-scope", "decisions", 1, "DECISION_MADE",
           SUBJECT_BACKUP, "2024-08-21T10:00:00Z", "2024-08-21T10:05:00Z",
           payload=_role("cancel", "exp-h")),
         E("ch9-h-release", "release-svc", 1, "STATE_CHANGED",
           "release-024", "2024-08-30T10:00:00Z", "2024-08-30T10:05:00Z",
           value="shipped", evidence_refs=("release-024",))],
        {"ch9-h2-scope": "Decision: backups are out of scope for this release.",
         "ch9-h-release": "Release 024 shipped."})
    h3_events, h3_texts = tail(
        [E("ch9-h3-arch", "decisions", 1, "STATE_CHANGED",
           "backup.system", "2024-08-21T10:00:00Z", "2024-08-21T10:05:00Z",
           value="replaced", payload=_role("supersede", "exp-h")),
         E("ch9-h-release", "release-svc", 1, "STATE_CHANGED",
           "release-024", "2024-08-30T10:00:00Z", "2024-08-30T10:05:00Z",
           value="shipped", evidence_refs=("release-024",))],
        {"ch9-h3-arch": "New architecture replaces the backup system entirely.",
         "ch9-h-release": "Release 024 shipped."})
    h4_events, h4_texts = tail(
        [E("ch9-h4-misc", "commit-119", 1, "OBSERVATION_RECORDED",
           "frontend.css", "2024-08-21T10:00:00Z", "2024-08-21T10:05:00Z"),
         E("ch9-h-release", "release-svc", 1, "STATE_CHANGED",
           "release-024", "2024-08-30T10:00:00Z", "2024-08-30T10:05:00Z",
           value="shipped", evidence_refs=("release-024",))],
        {"ch9-h4-misc": "unrelated frontend fix",
         "ch9-h-release": "Release 024 shipped."})
    return {
        "H1": (h1_events, h1_texts, "SATISFIED"),
        "H2": (h2_events, h2_texts, "CANCELLED"),
        "H3": (h3_events, h3_texts, "SUPERSEDED"),
        "H4": (h4_events, h4_texts, "OPEN"),
    }


def EXP_H() -> Expectation:
    return X("exp-h", SUBJECT_BACKUP, "PostgreSQL",
             "2024-07-17T10:00:00Z", ("session-051",), STMT_BACKUP,
             required_before="ch9-h-release")


# Truth labels for the canonical history (status as of 2024-08-31).
CANONICAL_TRUTH = {
    "intent-401": "SATISFIED",
    "exp-docs": "SATISFIED",
    "exp-docs-sem": "OPEN",  # semantic commit belongs to another fixture
    "exp-fixtures": "SATISFIED",
    "exp-tune": "SUPERSEDED",
    "exp-staging": "CANCELLED",
}

NOT_AN_EXPECTATION = ("ch9-redis-remark",)
