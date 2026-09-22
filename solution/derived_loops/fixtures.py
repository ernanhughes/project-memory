"""Fixtures: corpus_import consequences plus one stale-leg control.

Artifact IDs reuse the frozen running examples (adr-013, issue-088,
issue-089, partner-note-004, tests-compat-122, docs-note-012) and the
migration IDs (commit-118, commit-120). Snapshot IDs (snap-*) are
present-state observations with explicit dates so freshness is
testable. Never invent an ID outside this file; propose additions via
the continuity audit first.
"""

from __future__ import annotations

from .model import (
    CancellingEvidence,
    DerivedCandidate,
    Leg,
    ScopeTask,
    STANDPOINT,
)

# Legitimacy anchors: raw artifacts the gate accepts as traceable.
TRACEABLE = frozenset({
    "adr-013", "issue-088", "issue-089", "partner-note-004",
    "tests-compat-122", "docs-note-012",
    "commit-118", "commit-120",
    "snap-docs-0207", "snap-facade-0207", "snap-tests-0207",
    "snap-cli-0207", "snap-web-0207", "snap-backup-0827",
    "snap-stale-0102", "inferred-assumption",
})


def _cur(artifact: str, stmt: str, observed: str,
         traceable: bool = True) -> Leg:
    return Leg(kind="current", artifact_id=artifact, statement=stmt,
               observed_at=observed, inferred=False, traceable=traceable)


def _exp(artifact: str, stmt: str, observed: str,
         inferred: bool = False, traceable: bool = True) -> Leg:
    return Leg(kind="expected", artifact_id=artifact, statement=stmt,
               observed_at=observed, inferred=inferred,
               traceable=traceable)


def _cancel(kind: str, artifact: str, stmt: str) -> CancellingEvidence:
    return CancellingEvidence(kind=kind, artifact_id=artifact,
                              statement=stmt)


# Genuine hidden consequence: docs still describe removed flags.
C_DOCS_FLAGS = DerivedCandidate(
    candidate_id="c-docs-flags",
    subject="docs.corpus_import_flags",
    difference="docs still describe corpus_import flags removed by adr-013",
    current=_cur("snap-docs-0207",
                 "snapshot 2025-02-06: docs page lists corpus_import flags",
                 "2025-02-06"),
    expected=_exp("adr-013",
                  "adr-013 (2025-01-13): legacy corpus_import domain removed",
                  "2025-01-13"),
    ledger_genuine=True)

# False apparent consequence: facade deletion breaks a live contract.
C_FACADE = DerivedCandidate(
    candidate_id="c-facade-delete",
    subject="compat.facade",
    difference="delete the compatibility facade",
    current=_cur("snap-facade-0207",
                 "snapshot 2025-02-06: facade still serves partner traffic",
                 "2025-02-06"),
    expected=_exp("adr-013",
                  "adr-013: corpus_import domain removed",
                  "2025-01-13"),
    cancelling=(_cancel(
        "contract", "partner-note-004",
        "partner-note-004: preserve facade until end of Q1 2025"),),
    ledger_genuine=False, ledger_harmful_if_acted=True)

# Intentionally preserved stale reference: regression tests kept on purpose.
C_TESTS = DerivedCandidate(
    candidate_id="c-tests-remove",
    subject="tests.compat",
    difference="remove old corpus_import regression tests",
    current=_cur("snap-tests-0207",
                 "snapshot 2025-02-06: old tests still run and pass",
                 "2025-02-06"),
    expected=_exp("adr-013", "adr-013: domain removed", "2025-01-13"),
    cancelling=(_cancel(
        "intentional-preservation", "tests-compat-122",
        "tests-compat-122: regression tests remain intentionally"),),
    ledger_genuine=False)

# Scoped deferral: docs cleanup parked until after release. Explicit
# intention with a scope condition, not a derived loop at all.
C_DEFERRAL = DerivedCandidate(
    candidate_id="c-docs-deferral",
    subject="docs.cleanup",
    difference="update docs now",
    current=_cur("snap-docs-0207",
                 "snapshot 2025-02-06: docs still describe flags",
                 "2025-02-06"),
    expected=_exp("adr-013", "adr-013: domain removed", "2025-01-13"),
    cancelling=(_cancel(
        "deferral", "docs-note-012",
        "docs-note-012: documentation cleanup deferred until after release"),),
    ledger_genuine=False)

# Partial discharge: half the CLI callers migrated.
C_CLI_HALF = DerivedCandidate(
    candidate_id="c-cli-half",
    subject="callers.cli",
    difference="migrate remaining CLI callers off corpus_import",
    current=_cur("snap-cli-0207",
                 "snapshot 2025-02-06: 4 of 9 CLI call sites still import "
                 "corpus_import",
                 "2025-02-06"),
    expected=_exp("issue-088",
                  "issue-088: migrate CLI callers away from corpus_import",
                  "2025-01-14"),
    ledger_genuine=True)

# Second genuine: web callers, fully unmigrated in this snapshot.
C_WEB = DerivedCandidate(
    candidate_id="c-web",
    subject="callers.web",
    difference="migrate web callers off corpus_import",
    current=_cur("snap-web-0207",
                 "snapshot 2025-02-06: web call sites still import "
                 "corpus_import",
                 "2025-02-06"),
    expected=_exp("issue-089",
                  "issue-089: migrate web callers away from corpus_import",
                  "2025-01-14"),
    ledger_genuine=True)

# Stale-leg control: backup mismatch was real, resolved by commit-118.
# A snapshot from before the fix must not reopen it.
C_BACKUP_STALE = DerivedCandidate(
    candidate_id="c-backup-stale",
    subject="backup.backend",
    difference="move backup config to PostgreSQL",
    current=_cur("snap-stale-0102",
                 "snapshot 2024-08-01: backup config names SQLite "
                 "(superseded by commit-118 on 2024-08-27)",
                 "2024-08-01"),
    expected=_exp("adr-007" if False else "commit-118",
                  "commit-118: backup config moved to PostgreSQL",
                  "2024-08-27"),
    ledger_genuine=False)

# Guess control: expected leg itself inferred (no stated source).
C_GUESS = DerivedCandidate(
    candidate_id="c-guess",
    subject="perf.flags",
    difference="rebuild flag index (no stated expectation)",
    current=_cur("snap-docs-0207", "snapshot: flag page is slow",
                 "2025-02-06"),
    expected=_exp("inferred-assumption",
                  "assumed: flags should be indexed (never stated)",
                  "2025-02-06", inferred=True, traceable=True),
    ledger_genuine=False)


def all_tasks() -> list[ScopeTask]:
    full = (C_DOCS_FLAGS, C_FACADE, C_TESTS, C_DEFERRAL, C_CLI_HALF, C_WEB)
    return [
        ScopeTask(task_id="t-full-scope",
                  scope="corpus_import removal as of 2025-02-07",
                  standpoint=STANDPOINT, candidates=full,
                  explicit_obligations=("issue-088", "issue-089")),
        ScopeTask(task_id="t-hidden-only",
                  scope="docs flags consequence only",
                  standpoint=STANDPOINT,
                  candidates=(C_DOCS_FLAGS, C_GUESS),
                  explicit_obligations=()),
        ScopeTask(task_id="t-trap-only",
                  scope="facade plus preserved tests only (silence is correct)",
                  standpoint=STANDPOINT,
                  candidates=(C_FACADE, C_TESTS),
                  explicit_obligations=()),
        ScopeTask(task_id="t-deferral",
                  scope="docs cleanup under deferral",
                  standpoint=STANDPOINT,
                  candidates=(C_DEFERRAL, C_DOCS_FLAGS),
                  explicit_obligations=("docs-note-012",)),
        ScopeTask(task_id="t-partial",
                  scope="caller migration discharge",
                  standpoint=STANDPOINT,
                  candidates=(C_CLI_HALF, C_WEB, C_FACADE),
                  explicit_obligations=("issue-088", "issue-089")),
        ScopeTask(task_id="t-stale-leg",
                  scope="backup status with pre-fix snapshot",
                  standpoint=STANDPOINT,
                  candidates=(C_BACKUP_STALE, C_CLI_HALF),
                  explicit_obligations=()),
        ScopeTask(task_id="t-guess",
                  scope="inferred-expectation control",
                  standpoint=STANDPOINT,
                  candidates=(C_GUESS, C_WEB),
                  explicit_obligations=()),
        ScopeTask(task_id="t-contract-harm",
                  scope="facade under live contract",
                  standpoint=STANDPOINT,
                  candidates=(C_FACADE, C_WEB),
                  explicit_obligations=()),
    ]


def ledger_genuine(task: ScopeTask) -> set[str]:
    return {c.candidate_id for c in task.candidates if c.ledger_genuine}


def ledger_harmful(task: ScopeTask) -> set[str]:
    return {c.candidate_id for c in task.candidates
            if c.ledger_harmful_if_acted}
