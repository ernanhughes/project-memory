# Canonical running examples

Status: **CURRENT — continuity reference for the final 18-chapter Memory manuscript**

This document records the stable project histories used across the *Memory* manuscript, notebooks, fixtures, experiments, and capstone.

It is **not** a planning document, author-approval checklist, generator specification, or chapter edit list.

Its purpose is narrow:

> Keep recurring examples, dates, artifact identities, temporal cuts, and semantic traps consistent wherever they appear.

The current repository, preserved experiment artifacts, fixtures, implementation, and completed capstone remain authoritative for implementation and measured results. If one of those changes a canonical fact recorded here, update this document rather than creating a parallel history.

---

## Global rules

* The controlled history spans **2024-03-01 through 2027-06-30**.
* Every benchmark or capstone task that depends on temporal state has an explicit `as_of`.
* If a controlled case genuinely omits `as_of`, the corpus end is **2027-06-30**.
* Display IDs such as `session-031`, `adr-007`, and `evt-205` are stable artifact addresses. Their numeric suffixes do **not** encode chronology, chapter number, authority, relevance, or scenario.
* Distinct artifacts use globally unique numeric suffixes.
* Repeated references to one artifact retain the same ID.
* Dates below are calendar dates. When time-of-day matters, the fixture must state it explicitly.
* Human-readable descriptions should normally appear before artifact IDs in manuscript prose. IDs exist for traceability, not as facts the reader is expected to memorise.

---

# World A — Event-store migration

World A is the primary running example through the first half of the book.

Its central distinction is simple:

> The project can decide to use PostgreSQL before PostgreSQL is actually running in production.

That distinction must remain intact.

## Canonical timeline

| Date       | Artifact                                            | Role                         | Canonical event                                                                                                 |
| ---------- | --------------------------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------- |
| 2024-03-01 | `adr-003` / `evt-201`                               | decision                     | Use SQLite for the first production event store.                                                                |
| 2024-03-04 | `deployment-001` / `fact-301`                       | production state             | SQLite becomes the production event store.                                                                      |
| 2024-05-06 | `issue-041`                                         | task                         | SQLite performance-tuning work opens.                                                                           |
| 2024-06-14 | `session-014` / `evt-202`                           | evidence                     | Concurrent-write contention is observed under the target workload.                                              |
| 2024-06-19 | `session-019` / `evt-203`                           | benchmark                    | A controlled benchmark confirms the contention problem.                                                         |
| 2024-06-24 | `incident-021` / `evt-204`                          | incident                     | A concurrent importer run fails because of SQLite write contention.                                             |
| 2024-07-08 | `session-031`                                       | proposal                     | a.silva proposes moving the event store from SQLite to PostgreSQL.                                              |
| 2024-07-09 | `session-033`                                       | preference                   | j.lindqvist says they still prefer SQLite. This is neither support for PostgreSQL nor a decision.               |
| 2024-07-11 | `adr-007` / `evt-205`                               | decision                     | New event-store work should target PostgreSQL.                                                                  |
| 2024-07-15 | `commit-110`                                        | compatibility implementation | Compatibility mode is enabled before the schema and write-path changes.                                         |
| 2024-07-15 | `commit-112`                                        | staged implementation        | Application writes move to PostgreSQL on the migration branch and in staging. Production still runs SQLite.     |
| 2024-07-17 | `session-051` / `intent-401`                        | intention                    | Backup configuration still targets SQLite and must move before the next release.                                |
| 2024-07-19 | `validation-102`                                    | validation                   | Shadow reads from SQLite and PostgreSQL agree; the migration is cleared for production.                         |
| 2024-07-22 | `deployment-101` / `fact-302` / `migration-run-103` | production transition        | PostgreSQL becomes the production event store.                                                                  |
| 2024-07-23 | `fixture-scan-109`                                  | observed derived state       | Benchmark fixtures still encode SQLite timing and locking assumptions. This creates a real derived open loop.   |
| 2024-08-05 | `session-040`                                       | proposal                     | Redis is proposed for lookup latency.                                                                           |
| 2024-08-08 | `session-044`                                       | evidence                     | The working set fits in memory; Redis is judged unnecessary.                                                    |
| 2024-08-12 | `adr-009` / `evt-206`                               | decision                     | Do not introduce Redis.                                                                                         |
| 2024-08-16 | `runbook-006` / `evt-207`                           | derived restatement          | The runbook tells operators to use PostgreSQL. It echoes `adr-007`; it is not independent support.              |
| 2024-08-21 | `commit-117`                                        | silent completion            | Deployment documentation is updated without an explicit link to the earlier migration consequence.              |
| 2024-08-27 | `commit-118`                                        | completion                   | Backup configuration and its restore check move to PostgreSQL, completing `intent-401`.                         |
| 2024-08-30 | `release-024`                                       | release                      | The first product release after the migration ships.                                                            |
| 2024-09-03 | `commit-120`                                        | completion                   | PostgreSQL-aware benchmark fixtures replace the SQLite-dependent assumptions, closing the derived fixture loop. |
| 2024-10-07 | `session-072`                                       | follow-up                    | A new-service discussion assumes PostgreSQL. This supplies the Chapter 1 follow-up case.                        |

The human-readable arc is:

```text
SQLite works
→ contention appears
→ evidence accumulates
→ PostgreSQL is proposed
→ PostgreSQL is chosen
→ migration is staged and validated
→ PostgreSQL becomes production
→ consequences remain
→ consequences are later completed
```

Chapter prose does not need every date or ID every time this history appears.

---

## Proposal, preference, and decision

These three artifacts are deliberately easy to confuse:

| Artifact      | Meaning                        | Supports the PostgreSQL decision? |
| ------------- | ------------------------------ | --------------------------------: |
| `session-031` | PostgreSQL proposal            |                                no |
| `session-033` | Personal preference for SQLite |                                no |
| `adr-007`     | Recorded PostgreSQL decision   |                               yes |

Topical relevance is not authority.

A passage can discuss the right technology and still be the wrong evidence for what the project decided.

---

## Decision versus production state

Two claims coexist between 11 July and 22 July 2024.

### Architectural decision

`evt-205` / `adr-007`:

> New event-store work should target PostgreSQL.

Valid from **2024-07-11**.

### Production state

`fact-301`:

> SQLite runs in production.

Valid through **2024-07-21**.

`fact-302`:

> PostgreSQL runs in production.

Valid from **2024-07-22**.

Therefore, at:

```text
as_of: 2024-07-15
```

the correct answers are:

```text
What should new work target?  → PostgreSQL
What currently runs?          → SQLite
```

At and after 2024-07-22:

```text
What currently runs?          → PostgreSQL
```

This distinction is canonical.

---

## Evidence for the PostgreSQL decision

The migration rationale is supported by:

```text
session-014 / evt-202
    observed contention

session-019 / evt-203
    controlled benchmark

incident-021 / evt-204
    importer failure

          ↓

adr-007 / evt-205
    PostgreSQL decision
```

`runbook-006` is a later derived echo.

It can help locate or communicate the decision, but it does not become another independent reason for believing it.

---

## Redis sequence

The canonical Redis history is:

```text
session-040
    Redis proposed

session-044
    evidence says it is unnecessary

adr-009 / evt-206
    Redis rejected
```

`session-022` is retired and should not appear as the Redis proposal.

---

# Unfinished work after the migration

The book distinguishes explicit obligations, inferred consequences, silent completion, and supersession.

| Item                                      | Origin                       | State at 2024-08-23 | Final state                           |
| ----------------------------------------- | ---------------------------- | ------------------- | ------------------------------------- |
| Move backup configuration to PostgreSQL   | `session-051` / `intent-401` | open                | completed by `commit-118`, 2024-08-27 |
| Update deployment documentation           | migration consequence        | silently complete   | completed by `commit-117`, 2024-08-21 |
| Review SQLite-specific benchmark fixtures | `fixture-scan-109`           | open derived loop   | completed by `commit-120`, 2024-09-03 |
| Tune SQLite performance                   | `issue-041`                  | superseded          | superseded by PostgreSQL decision     |
| Ship first post-migration release         | release plan                 | scheduled           | `release-024`, 2024-08-30             |

The important evaluation cut is:

```text
as_of: 2024-08-23
```

At that point:

* backup work is genuinely open;
* documentation work is already complete, although its linkage is weak;
* fixture review is genuinely open but is a **derived consequence**, not an explicit authoritative obligation;
* `release-024` has not yet shipped.

The production deployment on 22 July is not the release referred to by `session-051`.

---

# World B — Compatibility boundary

World B tests whether memory can preserve a scoped commitment without turning every historical reference into unfinished work.

## Canonical timeline

| Date       | Artifact           | Canonical event                                                                                                   |
| ---------- | ------------------ | ----------------------------------------------------------------------------------------------------------------- |
| 2025-01-13 | `adr-013`          | Remove the legacy `corpus_import` domain. Retain a compatibility facade only for the external partner commitment. |
| 2025-01-14 | `issue-088`        | Migrate CLI callers away from `corpus_import`.                                                                    |
| 2025-01-14 | `issue-089`        | Migrate web callers away from `corpus_import`.                                                                    |
| 2025-01-16 | `partner-note-004` | Preserve the partner-facing facade **until the end of Q1 2025**.                                                  |
| 2025-01-22 | `issue-088`        | CLI migration completes.                                                                                          |
| 2025-01-29 | `issue-089`        | Web migration completes.                                                                                          |
| 2025-01-30 | `tests-compat-122` | Partner-facade regression tests remain intentionally.                                                             |
| 2025-01-31 | `docs-note-012`    | Documentation cleanup is explicitly deferred.                                                                     |

Canonical interpretation:

* `adr-013` removes the legacy domain.
* It does **not** move the entire legacy domain behind a facade.
* CLI and web migration are separate tasks.
* The facade remains only because of a scoped external commitment.
* Old-looking tests are intentional.
* Deferred documentation is not forgotten caller-migration work.

World B is therefore strongly associated with **correct abstention**.

---

# World C — Migration procedure and learning

World C is used when the book moves from remembering individual episodes toward learning from repeated experience.

The procedural claim is:

```text
For a breaking schema migration:

1. introduce compatibility behaviour;
2. apply the schema change;
3. shadow-read both representations;
4. validate;
5. remove compatibility only after the checks pass.
```

This is not introduced as timeless truth.

It is earned from a history of successes and failures and later becomes superseded.

## Canonical episodes

| Date       | Artifact            | Role                   | Canonical event                                                                                                          |
| ---------- | ------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 2024-07-22 | `migration-run-103` | early success          | Event-store migration succeeds after compatibility, write-path change, shadow reads, and validation.                     |
| 2024-11-14 | `incident-026`      | failure                | Schema-first migration removes or renames a column still read by live code, causing a nine-minute outage until rollback. |
| 2025-02-11 | `incident-105`      | failure                | Schema-first migration breaks a live caller before compatibility behaviour is available.                                 |
| 2025-03-20 | `staging-run-104`   | failure                | Schema-first staging migration invalidates the old reader before the compatibility path is deployed.                     |
| 2025-04-10 | `run-124`           | independent success    | Compatibility-first production migration succeeds with shadow reads and validation.                                      |
| 2025-04-15 | `procedure-123`     | consolidated procedure | The compatibility-first sequence becomes the project procedure for breaking schema migrations.                           |
| 2026-02-10 | `change-061`        | exception              | A small additive migration is safe without the full breaking-change procedure.                                           |
| 2027-03-15 | `platform-note-125` | supersession           | A platform change removes the assumptions behind `procedure-123`; the procedure is no longer current.                    |

`procedure-123` is therefore:

* a **2025 procedure**, not a 2026 procedure;
* scoped to breaking schema migrations;
* valid only while its prerequisites hold;
* no longer current after 2027-03-15.

---

## Consolidation traps

### Derived echo

`staging-log-018` restates `incident-026`.

It is not an independent failure episode.

Exactly three schema-first failure episodes support the pattern:

```text
incident-026
incident-105
staging-run-104
```

### Similar symptom, different cause

`incident-106` resembles the nine-minute migration outage but is caused by network saturation.

It must not reinforce the schema-ordering procedure.

### Exception

`change-061` demonstrates that the full procedure is not universal.

An additive migration can be safe without the complete breaking-change sequence.

These cases protect the book from turning repeated correlation into an unconditional rule.

---

# Strategy X — Hidden prerequisite failure

`incident-034`, dated **2025-06-18**, defines Strategy X.

The mechanism is specific:

> Strategy X disables foreign-key checks before copying rows. An exception occurs before the checks are restored, allowing orphaned rows.

The missing prerequisite is:

```text
exception-safe restoration of foreign-key enforcement
+
clean foreign-key validation before completion
```

Canonical outcome:

> **orphaned-row corruption caused by an unmet foreign-key restoration prerequisite**

Do not replace this with a vague “migration failure” or change the mechanism between chapters.

Strategy X serves several teaching roles:

* a rare, expensive failure worth retaining;
* a near-miss for blindly replayed procedure;
* a reminder that similarity to past success is insufficient when a hidden prerequisite differs;
* a capstone constraint for the importer-index/backfill task.

---

# World D — Task-relative context

World D supplies explicit task dates so that context selection can be judged against what was knowable and current at the time.

## Context-selection task

```text
task: task-107
as_of: 2024-12-02
goal: plan the next importer schema migration
```

Relevant artifacts include:

| Date       | Artifact          | Meaning                                                                   |
| ---------- | ----------------- | ------------------------------------------------------------------------- |
| 2024-04-18 | `benchmark-128`   | Old SQLite-only importer baseline.                                        |
| 2024-09-06 | `policy-129`      | Schema migrations must be reversible and include a passing rollback test. |
| 2024-09-12 | `requirement-127` | Importer must accept the v1 event representation until 2025-06-30.        |
| 2024-11-14 | `incident-026`    | Nine-minute schema-first migration outage.                                |
| 2024-11-25 | `benchmark-126`   | PostgreSQL importer baseline superseding `benchmark-128`.                 |
| 2024-12-02 | `task-107`        | Current planning task.                                                    |

`session-019` remains valid historical support for the PostgreSQL decision.

It is not the superseded benchmark.

The genuinely superseded benchmark is `benchmark-128`.

---

## Later compatibility-release task

```text
task: task-108
as_of: 2025-02-07
release: release-121
release date: 2025-02-14
```

This task can legitimately see:

* `incident-026`;
* `adr-013`;
* `issue-088`;
* `issue-089`;
* `partner-note-004`;
* the corresponding caller-migration outcomes.

It is not the August 2024 `release-024` task.

By this point:

* backup debt from World A is complete;
* the benchmark-fixture loop is complete;
* those histories may remain available but should not masquerade as current unfinished work.

---

# Trust fixtures

These fixtures support the trust and admission boundary used in the final part of the book.

| ID            | Date       | Kind                            | Canonical meaning                                                                                    |
| ------------- | ---------- | ------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `session-501` | 2024-07-18 | hostile instruction carrier     | Claims importer migrations may skip rollback validation; contradicts the current reversibility rule. |
| `session-502` | 2024-07-16 | unverified hearsay              | Unconfirmed claim about partner flexibility.                                                         |
| `runbook-503` | 2024-08-02 | unjustified derived restatement | Claims operators may skip validation; its content exceeds its source.                                |
| `runbook-504` | 2024-08-10 | repeated derived claim          | First of several same-root restatements about skipping rollback checks.                              |
| `runbook-505` | 2024-08-11 | repeated derived claim          | Second same-root restatement.                                                                        |
| `session-506` | 2024-08-12 | repeated derived claim          | Third same-root restatement in session form.                                                         |
| `adr-507`     | 2024-07-11 | cross-scope decision            | A different project's event-store decision uses SQLite. Plausible but out of scope.                  |
| `session-508` | 2024-06-19 | revoked evidence                | Contention benchmark later revoked on 2024-09-01.                                                    |
| `runbook-509` | 2024-08-02 | derived from revoked source     | Restatement derived from `session-508`; it must not silently regain authority.                       |
| `session-510` | 2024-08-21 | restricted evidence             | Contention figures restricted to the release-team scope.                                             |

Canonical trust rules:

* hostile content travels through ordinary artifacts rather than carrying an evaluator-visible “malicious” label;
* revocation and restriction are explicit registry state;
* repeated restatements sharing one lineage are not independent corroboration;
* cross-project evidence remains distinguishable by scope;
* derived items retain resolvable lineage;
* something may remain historically informative while being inadmissible for current action.

---

# Capstone task families

The capstone does **not** have one universal historical cut.

Each task family has its own `as_of`.

| Family                         | Present task                                                         |    `as_of` | Key history                                                                                |
| ------------------------------ | -------------------------------------------------------------------- | ---------: | ------------------------------------------------------------------------------------------ |
| Continue unfinished work       | Continue the event-store migration and prepare the next safe change. | 2024-08-23 | Backup obligation open; docs silently complete; fixture review open; release still future. |
| Respect current architecture   | Add a persistence feature.                                           | 2024-10-07 | PostgreSQL is current; SQLite implementation choices are historical.                       |
| Avoid known failed approaches  | Add a covering index, including schema change and row backfill.      | 2025-06-23 | `incident-026` and Strategy X constrain the safe implementation.                           |
| Use project-specific procedure | Run the next breaking schema migration.                              | 2025-07-01 | `procedure-123` exists; Strategy X supplies a hidden-prerequisite near miss.               |
| Recover rationale              | Should we switch back to SQLite?                                     | 2024-08-23 | `adr-007` and its evidence chain are available; later World C history is excluded.         |
| Detect relevant constraint     | Simplify this module.                                                | 2025-02-07 | Partner facade remains protected through the end of Q1 2025.                               |

Each family also has a matched case in which memory should **not** change the correct behaviour.

That distinction is fundamental:

```text
memory should matter
    relevant history changes the correct action

memory should not matter
    no relevant historical constraint exists
```

Useful memory must succeed at both.

---

## Capstone comparison conditions

The canonical comparison ladder is:

1. **No persistent memory** — present task plus permitted non-memory context.
2. **Naive retrieval** — ordinary top-ranked project history.
3. **Structured memory** — the earned structured system under test.
4. **Oracle memory** — evaluator supplies exactly the ledger-derived relevant memory required by the task.

Oracle memory is an upper-bound diagnostic.

It is not a deployable architecture and must never be described as one.

---

# Current chapter use

The final book contains **18 chapters**.

This document no longer maintains a per-chapter edit checklist. Chapter content is authoritative for exposition; this document is authoritative only for continuity of the shared examples.

The broad use of these worlds in the current book is:

```text
Chapters 1–8
    event-store history, retrieval, interpretation,
    association, routing, provenance, temporal state

Chapters 9–14
    unfinished work, consequences, task-relative relevance,
    behavioural use, framing, bounded context

Chapter 15
    what should continue to compete for future use

Chapter 16
    learning from outcomes, adaptation, repeated episodes,
    procedures and their prerequisites

Chapter 17
    trust, admission, scope, revocation, corroboration,
    poisoning and must-retain failures

Chapter 18
    the completed remembering system and capstone integration
```

Do not create references to Chapters 19 or 20.

---

# Continuity invariants

The following facts are load-bearing and should not drift between manuscript, notebooks, fixtures, experiments, and capstone.

### Event-store chronology

```text
SQLite decision             2024-03-01
SQLite production           2024-03-04
contention evidence         June 2024
PostgreSQL decision         2024-07-11
PostgreSQL production       2024-07-22
first later release         2024-08-30
Chapter 1 follow-up         2024-10-07
```

### Decision is not production

From 11–21 July 2024:

```text
new work → PostgreSQL
production → SQLite
```

### Redis

```text
session-040 → session-044 → adr-009
```

### Provenance

```text
runbook-006
    derives from the PostgreSQL decision
    does not independently support it
```

### Open-work cut

At 2024-08-23:

```text
backup obligation        open
documentation update     already complete
fixture review           open derived loop
release-024              future
```

### Schema procedure

Three canonical schema-first failures:

```text
incident-026
incident-105
staging-run-104
```

`staging-log-018` is only a derived echo.

### Strategy X

```text
foreign-key checks disabled
→ exception
→ checks not safely restored
→ orphaned rows
```

### Procedure validity

```text
procedure-123
valid from 2025-04-15
superseded 2027-03-15
```

### Corpus end

```text
2027-06-30
```

---

# How manuscript prose should use this file

This document is deliberately more precise than the published narrative needs to be.

The manuscript should normally prefer:

> the PostgreSQL decision

over:

> `adr-007`

and:

> a few months later

over an exact date when chronology is not the idea being taught.

Use the precise artifact ID or date when it performs real explanatory work:

* provenance;
* temporal reasoning;
* supersession;
* reproducibility;
* evidence inspection;
* fixture definition;
* experiment reporting.

Do not make the reader memorise this ledger.

This file exists so the **book does not have to**.
