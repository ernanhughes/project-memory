# Canonical running examples

Status: **AUTHOR CHECKPOINT — all known continuity conflicts resolved; no generator or fixture work before merge approval**

This document is the shared source of truth for the *Memory* manuscript, the controlled corpus, and the Project Memory capstone. It preserves manuscript facts where they are coherent. Every fact introduced to reconcile conflicting drafts is marked **RECONCILIATION — author to approve**.

## Global time and identifier rules

- The corpus spans **2024-03-01 through 2027-06-30**.
- Every benchmark query has an explicit `as_of` timestamp. If a case omits it, evaluation uses the corpus end, **2027-06-30**, rather than an implicit present.
- Book artifact IDs such as `session-031` and `evt-201` are display labels only. Their numbers do not encode chronology, day of month, scenario, relevance, authority, or chapter number.
- Every numeric suffix is globally unique across all display-ID prefixes. Two distinct artifacts may not share a suffix, even when their prefixes differ. Repeated references to the same artifact retain its one ID.
- The future generator must assign separate internal IDs that increase with ingestion order and carry no scenario or date signal. A suitable shape is `gen-000001`. Display IDs remain in artifact content.
- The `evt-2xx` allocation is retained, but the global uniqueness rule applies to every prefix.
- Dates below are calendar dates. Where time-of-day affects evaluation, a fixture must state it explicitly.

## World A — event-store migration

### Canonical timeline

| Date | Artifact | Kind | Canonical event |
|---|---|---|---|
| 2024-03-01 (Friday) | `adr-003` / `evt-201` | decision | Use SQLite for the first production event store. |
| 2024-03-04 (Monday) | `deployment-001` / `fact-301` | production state | SQLite becomes the production event store. |
| 2024-05-06 (Monday) | `issue-041` | task | SQLite performance-tuning work opens.  |
| 2024-06-14 (Friday) | `session-014` / `evt-202` | evidence | Concurrent-write contention is observed under the target workload. |
| 2024-06-19 (Wednesday) | `session-019` / `evt-203` | benchmark | A controlled benchmark confirms the contention problem. |
| 2024-06-24 (Monday) | `incident-021` / `evt-204` | incident report | A concurrent importer run fails because of SQLite write contention.  |
| 2024-07-08 (Monday) | `session-031` | proposal | a.silva proposes moving the event store from SQLite to PostgreSQL. |
| 2024-07-09 (Tuesday) | `session-033` | preference | j.lindqvist says, “I still prefer SQLite.” This is neither support for PostgreSQL nor a decision. |
| 2024-07-11 (Thursday) | `adr-007` / `evt-205` | decision | New event-store work should target PostgreSQL. |
| 2024-07-15 (Monday) | `commit-110` | compatibility implementation | Compatibility mode is enabled on the migration branch and in staging before the schema and write-path changes. **RECONCILIATION — author approval recorded by merge.** |
| 2024-07-15 (Monday) | `commit-112` | staged implementation | On the migration branch, application writes are changed to PostgreSQL and exercised in staging after compatibility mode is enabled. Production still runs SQLite. |
| 2024-07-17 (Wednesday) | `session-051` / `intent-401` | intention | Backup configuration still targets SQLite and must move before release. |
| 2024-07-19 (Friday) | `validation-102` | validation | Staging shadow reads from SQLite and PostgreSQL agree; the migration is cleared for production. **RECONCILIATION — author approval recorded by merge.** |
| 2024-07-22 (Monday) | `deployment-101` / `fact-302` / `migration-run-103` | production state and success episode | PostgreSQL becomes the production event store after compatibility mode, schema/write-path change, shadow reads, and validation. This deployment is not the release named in `session-051`. |
| 2024-08-05 (Monday) | `session-040` | proposal | Redis is proposed for lookup latency. |
| 2024-08-08 (Thursday) | `session-044` | evidence | The working set fits in memory; Redis is judged unnecessary. |
| 2024-08-12 (Monday) | `adr-009` / `evt-206` | decision | Do not introduce Redis. |
| 2024-08-16 (Friday) | `runbook-006` / `evt-207` | derived restatement | The runbook tells operators to use PostgreSQL, echoing `adr-007`; it is derived evidence, not independent support. |
| 2024-07-23 (Tuesday) | `fixture-scan-109` | observed state | The benchmark fixtures still encode SQLite timing and locking assumptions; fixture review is a true derived loop at this date. **RECONCILIATION — author approval recorded by merge.** |
| 2024-08-21 (Wednesday) | `commit-117` | silent completion | A commit titled “refresh deploy docs” updates the deployment documentation without linking back to the earlier obligation. **RECONCILIATION — author approval recorded by merge.** |
| 2024-08-27 (Tuesday) | `commit-118` | completion | Backup configuration and its restore check move to PostgreSQL, completing `intent-401` before release. **RECONCILIATION — author approval recorded by merge.** |
| 2024-09-03 (Tuesday) | `commit-120` | completion | PostgreSQL-aware benchmark fixtures replace the SQLite-dependent assumptions, closing the derived fixture loop. **RECONCILIATION — author approval recorded by merge.** |
| 2024-08-30 (Friday) | `release-024` | release outcome | The first product release after the migration ships. |
| 2024-10-07 (Monday) | `session-072` | follow-up | A new-service discussion assumes PostgreSQL and supplies the Chapter 1 follow-up.  |

The approved book arc is March → June → July 2024. The SQLite tuning task opens in May. Chapter 1’s follow-up moves to October 2024. The corpus ends on 2027-06-30.

The canonical Redis sequence is `session-040` → `session-044` → `adr-009`. `session-022` is retired.

### Proposal, preference, and decision trap

The three Chapter 4 passages must remain distinct:

| Artifact | Speech act | Supports the current PostgreSQL decision? | Why |
|---|---|---:|---|
| `session-031` | proposal | no | It introduces an option but does not settle it. |
| `session-033` | personal preference for SQLite | no | It is a preference for the losing option and is the E-04 distractor. |
| `adr-007` | recorded decision | yes | It is the authoritative decision source. |

E-04 must retain all three passages. Chapter 7 must retain `session-033` as a non-supporting distractor.

### Decision and production state

A decision about what new work should target and a fact about what currently runs are separate claims.

```yaml
event_id: evt-205
kind: decision
topic: event-store target
content: New event-store work should target PostgreSQL.
actors:
  - m.okafor
  - j.lindqvist
decided_at: 2024-07-11
valid_from: 2024-07-11
valid_until: null
supersedes:
  - evt-201
supported_by:
  - evt-202
  - evt-203
  - evt-204
source:
  - adr-007
status: current
```

```yaml
event_id: fact-301
kind: production_state
topic: production event-store backend
content: SQLite runs in production.
actors:
  - m.okafor
effective_at: 2024-03-04
valid_from: 2024-03-04
valid_until: 2024-07-22
supersedes: []
supported_by:
  - deployment-001
source:
  - deployment-001
status: superseded
```

```yaml
event_id: fact-302
kind: production_state
topic: production event-store backend
content: PostgreSQL runs in production.
actors:
  - m.okafor
effective_at: 2024-07-22
valid_from: 2024-07-22
valid_until: null
supersedes:
  - fact-301
supported_by:
  - deployment-101
source:
  - deployment-101
status: current
```

At `as_of: 2024-07-15`, “What should new code target?” resolves to PostgreSQL, while “What runs in production?” resolves to SQLite. At and after 2024-07-22, the production-state answer is PostgreSQL.

### Provenance fixtures and legacy event mapping

| Old manuscript event | Canonical event | Source artifact | Date | Role |
|---|---|---|---|---|
| `legacy-event-A` | `evt-201` | `adr-003` | 2024-03-01 | Earlier SQLite decision, superseded by `evt-205`. |
| `legacy-event-B` | `evt-203` | `session-019` | 2024-06-19 | Benchmark evidence supporting migration. |
| `legacy-event-C` | `evt-204` | `incident-021` | 2024-06-24 | Incident evidence supporting migration. |
| none | `evt-207` | `runbook-006` | 2024-08-16 | Derived echo of `adr-007`, not independent support. |

The old `legacy-event-A`, `legacy-event-B`, `legacy-event-C`, and `legacy-event-D` labels must not survive in regenerated fixtures. This prevents the `legacy-event-D` / `session-014` collision.

### Intentions and release boundary

| Intention | Opened | Deadline | Desired state | At 2024-08-23 | At corpus end |
|---|---|---|---|---|---|
| Move backup configuration to PostgreSQL | `session-051`, 2024-07-17 | before `release-024`, 2024-08-30 | Backups target and restore PostgreSQL | unresolved | completed by `commit-118` on 2024-08-27 |
| Update deployment documentation | migration consequence | none recorded | Documentation names PostgreSQL | completed silently by `commit-117` on 2024-08-21 | completed |
| Review SQLite-specific benchmark fixtures | migration consequence; state confirmed by `fixture-scan-109` | none recorded | Fixtures represent the PostgreSQL system | true derived loop: fixtures are SQLite-dependent | completed by `commit-120` on 2024-09-03 |
| Tune SQLite performance | `issue-041`, 2024-05-06 | none recorded | Improve SQLite contention | superseded by `evt-205` | superseded |
| Ship first post-migration release | release plan | 2024-08-30 | Release is shipped | scheduled | completed by `release-024` on 2024-08-30 |

The “continue unfinished work” capstone cut is `as_of: 2024-08-23`, one week before `release-024`. At that cut the backup obligation is open, the documentation work is already complete despite the weak linkage, and the fixture review is only a derived candidate. The 22 July production deployment is not the release referred to by `session-051`.

At the corpus end, `intent-401` is completed, `release-024` has shipped, and the true fixture loop is completed. No open item is left without an end-of-corpus state.

Documentation and fixture work remain useful traps: absence of an explicit task link must not hide `commit-117`, while the fixture loop is genuinely open at 2024-08-23 because `fixture-scan-109` confirms stale SQLite assumptions. It closes only with `commit-120` on 2024-09-03.

## World B — compatibility boundary

These dates, actors, and meanings are approved for v0.1.

| Date | Artifact | Actor(s) | Kind | Proposed canonical event |
|---|---|---|---|---|
| 2025-01-13 | `adr-013` | a.silva, m.okafor | decision | Remove the legacy `corpus_import` domain. Keep a compatibility facade only for the external partner commitment. |
| 2025-01-14 | `issue-088` | a.silva | task | Migrate CLI callers away from `corpus_import`. |
| 2025-01-14 | `issue-089` | m.okafor | task | Migrate web callers away from `corpus_import`. |
| 2025-01-16 | `partner-note-004` | j.lindqvist | constraint | Preserve the partner-facing facade “until the end of Q1 2025”, expiring after 2025-03-31. |
| 2025-01-22 | `issue-088` | a.silva | outcome | CLI caller migration completes. |
| 2025-01-29 | `issue-089` | m.okafor | outcome | Web caller migration completes. |
| 2025-01-30 | `tests-compat-122` | a.silva | constraint | Regression tests for the partner facade remain intentionally. |
| 2025-01-31 | `docs-note-012` | m.okafor | scoped deferral | Documentation cleanup is deferred; it is not an open caller-migration task. |

This preserves Chapter 11’s distinction:

- `adr-013` removes the legacy domain; it does not move the domain wholesale behind a facade.
- `issue-088` and `issue-089` migrate CLI and web callers respectively.
- The compatibility facade exists for the unambiguous partner commitment, “until the end of Q1 2025”. An ambiguous variant is deferred beyond v0.1.
- Retained tests and deferred documentation must not be misreported as forgotten migration work.

This world primarily tests correct abstention. A system that reports every old-looking reference as unfinished cleanup fails.

## World C — migration procedure

Canonical procedural claim under test:

```text
For a breaking schema migration:
1. introduce compatibility behaviour;
2. apply the schema change;
3. shadow-read both representations;
4. validate;
5. remove compatibility only after the checks pass.
```

The following World C additions reconcile conflicting chapter drafts. They remain **RECONCILIATION** facts until author approval is recorded by merging this change.

### Episodes from which the pattern may be consolidated

| Date | Artifact | Actor(s) | Role | Canonical event |
|---|---|---|---|---|
| 2024-07-22 | `migration-run-103` | a.silva, m.okafor | early success | The event-store migration succeeds after compatibility mode is enabled, the write path changes, shadow reads agree, and validation passes. **RECONCILIATION — author approval recorded by merge.** |
| 2024-11-14 | `incident-026` | m.okafor | failure 1 | A schema-first migration drops or renames a column that live code still reads, causing a nine-minute outage until rollback. |
| 2025-02-11 | `incident-105` | a.silva | failure 2 | A schema-first migration breaks a live caller before compatibility behaviour is available. **RECONCILIATION — author approval recorded by merge.** |
| 2025-03-20 | `staging-run-104` | j.lindqvist | failure 3 | A schema-first staging migration invalidates the old reader before the compatibility path is deployed. **RECONCILIATION — author approval recorded by merge.** |
| 2025-04-10 | `run-124` | j.lindqvist | independent success | A compatibility-first production migration completes with shadow reads and validation, avoiding the three earlier failure modes. **RECONCILIATION — author approval recorded by merge.** |
| 2025-04-15 | `procedure-123` | j.lindqvist | procedure record | The compatibility-first sequence is recorded as the project procedure for breaking schema migrations. It is the 2025 procedure, not a “2026 procedure”. **RECONCILIATION — author approval recorded by merge.** |
| 2026-02-10 | `change-061` | m.okafor | exception | A small additive migration is safe without the full breaking-change sequence. |
| 2027-03-15 | `platform-note-125` | j.lindqvist | supersession | A platform change removes the assumptions behind `procedure-123`; the procedure is no longer current. |
| 2027-06-30 | corpus boundary | evaluator | end state | The corpus closes; unresolved current claims are evaluated at this date unless a query supplies another `as_of`. |

`session-019` remains the World A PostgreSQL contention benchmark. It is not a schema-migration episode.

### Consolidation traps

| Date | Artifact | Trap | Ground truth |
|---|---|---|---|
| 2024-11-18 | `staging-log-018` | echo mistaken for independent support | It restates `incident-026`; its derivation edge points to that incident, so it adds no independent failure episode. **RECONCILIATION — author approval recorded by merge.** |
| 2025-04-15 | `procedure-123` validity | timeless pattern | The pattern is valid only from 2025-04-15 through 2027-03-14 and only for breaking schema migrations on the old platform. **RECONCILIATION — author approval recorded by merge.** |
| 2025-08-12 | `incident-106` | same symptom, different cause | A nine-minute-looking timeout is caused by network saturation, not schema ordering. It must not reinforce the compatibility-first schema claim. **RECONCILIATION — author approval recorded by merge.** |

Chapter 15 therefore has exactly three schema-first failure episodes: `incident-026`, `incident-105`, and `staging-run-104`. The similarly named `staging-log-018` is only an echo.

### Strategy X: one mechanism, two evaluation roles

| Date | Artifact | Actor | Canonical fact |
|---|---|---|---|
| 2025-06-18 | `incident-034` | a.silva | Strategy X disables foreign-key checks before copying rows and fails to restore them after an exception, permitting orphaned rows. The hidden prerequisite is an exception-safe restoration guard plus a clean foreign-key validation before Strategy X may run. |

This single failure serves two roles without changing mechanism:

- Chapter 17: a rare, high-cost failure that must remain available even when old.
- Chapter 19: a superficially similar migration whose hidden prerequisite makes blind procedure replay unsafe.

Chapter 20 must call the outcome **orphaned-row corruption caused by an unmet foreign-key restoration prerequisite**, not alternate between “corruption” and an unspecified failed prerequisite.

The former “March outage” references in Chapters 12, 19, and 20 must point to `incident-026` on 2024-11-14. In March 2024, production still ran SQLite.

## World D — dated task and context fixtures

**RECONCILIATION — author approval recorded by merge:** every World D artifact, date, actor, and task boundary in this section was introduced to reconcile chapter timelines. None is self-approved by this ledger.

### Chapter 12 context-selection task

The Chapter 12 task is evaluated at `as_of: 2024-12-02`, after `incident-026`.

| Date | Artifact | Kind | Canonical fact |
|---|---|---|---|
| 2024-04-18 | `benchmark-128` | benchmark | An early SQLite-only importer throughput baseline. |
| 2024-09-06 | `policy-129` | current rule | All schema migrations must be reversible and include a passing rollback test. |
| 2024-09-12 | `requirement-127` | current constraint | The importer must accept the v1 event representation until 2025-06-30. |
| 2024-11-25 | `benchmark-126` | benchmark | The PostgreSQL importer baseline supersedes `benchmark-128`. |
| 2024-12-02 | `task-107` | task | Assemble the context needed to plan the next importer schema migration. |

For `task-107`, `session-019` remains live supporting evidence for the 2024 backend decision. The genuinely superseded benchmark is `benchmark-128`, superseded by `benchmark-126`. The current reversibility rule and importer compatibility requirement are admissible constraints.

### Chapter 14 later-release task

The Chapter 14 release-context task is not `release-024`.

| Date | Artifact | Kind | Canonical fact |
|---|---|---|---|
| 2025-02-07 | `task-108` | task | Assemble the smallest sufficient context for the February compatibility release. |
| 2025-02-14 | `release-121` | release | The later release ships after the World B caller migrations and after the November outage incident. |

`task-108` uses `as_of: 2025-02-07`. It may therefore contain `incident-026`, `adr-013`, `issue-088`, `issue-089`, `partner-note-004`, and their outcomes. It must not be described as the August 2024 release task.

## Capstone task families

Each family carries its own `as_of`; there is no single capstone cut.

| Family | Task | `as_of` | Required history boundary |
|---|---|---:|---|
| Continue unfinished work | Continue the event-store migration and prepare the next safe change. | 2024-08-23 | Backup work is open; docs are silently complete; release is still future. |
| Respect current architecture | Add a persistence feature. | 2024-10-07 | PostgreSQL is current and SQLite-era implementation patterns are historical. |
| Avoid known failed approaches | Speed up an importer query by adding a covering index, including the required schema change and row backfill. | 2025-06-23 | `incident-026` warns against changing a live schema before compatible code; Strategy X `incident-034` warns against a backfill that disables foreign-key checks without exception-safe restoration and validation. |
| Use project-specific procedure | Run the next breaking schema migration. | 2025-07-01 | `procedure-123` exists and Strategy X supplies a hidden-prerequisite near miss. |
| Recover rationale | Should we switch back to SQLite? | 2024-08-23 | `adr-007` and its evidence chain exist; later World C events are excluded. |
| Detect relevant constraint | Simplify this module. | 2025-02-07 | The partner facade is protected through the end of Q1 2025. |

Every family also has a matched memory-should-not-matter case at the same `as_of`. A fixture may contain only artifacts dated on or before its family cut.

The “continue unfinished work” family may need to recover:

- the current PostgreSQL target and production-state facts;
- the rejected Redis proposal;
- the unresolved backup obligation and its release deadline;
- the silently completed documentation update;
- the fixture-review candidate without promoting it to an obligation;
- exact provenance for every supplied item.

### Comparison conditions

1. **No persistent memory:** the system receives only the present task and permitted non-memory context.
2. **Naive retrieval:** the system receives the baseline retriever’s top-ranked history.
3. **Structured memory:** the smallest structured system whose preceding experiments returned Type-A.
4. **Oracle memory:** the evaluator supplies exactly the ledger-derived, task-relevant memory items needed for the case. This is an upper bound, not a deployable system.

The capstone must report how much of the gap between no-memory and oracle-memory performance each implemented condition captures. It must not imply that the oracle is attainable.

### Per-layer ablations

For every structured layer that survives its preceding experiment, run a matched ablation that removes only that layer while keeping the remaining system and task packet fixed. Candidate layers are:

- event structure;
- support and derivation edges;
- validity and supersession resolution;
- intention and loop state;
- context assembly policy;
- later consolidation, compression, availability, attribution, or procedure layers only if the book has earned and implemented them.

Do not ablate layers that were never implemented or whose prerequisite experiment returned Type-B.

### Matched controls

- **Memory should matter:** relevant project history changes the correct implementation or restraint.
- **Memory should not matter:** no relevant historical constraint exists, so memory should not change the correct behaviour.

## Per-chapter edit list

These edits are required before the manuscript and generated corpus can both claim this ledger as ground truth.

| Chapter | Required edits |
|---|---|
| 1 | Replace the January migration decision with `adr-007` on 2024-07-11. Replace the April follow-up with `session-072` in October 2024. |
| 2 | Replace old `legacy-event-A/011/012/014` IDs with `evt-201/203/204/205`. Distinguish the 11 July decision from the 22 July production state. |
| 3 | Retire `session-022`; use `session-040`, `session-044`, and `adr-009` for Redis. Use `session-014` only for the contention observation. |
| 4 | Preserve Monday `session-031` proposal, Tuesday `session-033` SQLite preference, and Thursday `adr-007` decision. The proposal actor is a.silva. |
| 5 | Keep a.silva as the `session-031` proposer. Change “Friday” to Thursday for `adr-007`; do not give the decision an immediate production outcome. |
| 6 | Keep proposals, preferences, decisions, and production facts as separate candidate passages. |
| 7 | Replace the January stress test with `session-019` on 2024-06-19 and the March importer incident with `incident-021` on 2024-06-24. Use `session-033` as a non-supporting distractor and `runbook-006` as a derived echo. |
| 8 | Preserve the March → June → July arc. The target decision is current from 11 July; PostgreSQL production state begins 22 July. Production facts use `effective_at`, not `decided_at`. |
| 9 | Date `issue-041` to 2024-05-06. Add silent completion artifact `commit-117` (“refresh deploy docs”). Keep `intent-401` open at 23 August, completed by `commit-118` on 27 August, and tie release to `release-024` on 30 August. |
| 10 | Use the explicit backup obligation from `session-051`; keep the fixture revision as a derived candidate, not an authoritative task. |
| 11 | `adr-013` removes the legacy domain; `issue-088` migrates CLI callers; `issue-089` migrates web callers. Quote the partner commitment as “until the end of Q1 2025”. |
| 12 | Date the task to 2024-12-02. Replace the March outage claim with the nine-minute outage in `incident-026` on 2024-11-14. Add `policy-129` reversibility, `requirement-127` importer compatibility, and superseded `benchmark-128`/current `benchmark-126`; do not call `session-019` superseded. |
| 13 | Keep decision retrieval separate from production-state retrieval and require explicit `as_of` values. |
| 14 | Make the context-assembly task `task-108` at 2025-02-07 for `release-121` on 2025-02-14. This permits the November incident and January 2025 caller migrations in one timeline. Remove the backup debt from current context or label it completed by `commit-118`; label the fixture warning historical and completed by `commit-120`. Preserve derivation distinctions such as `runbook-006`. |
| 15 | Replace the locking account with the nine-minute outage caused by removing or renaming a column still read by live code. Replace `session-019` in the schema-failure set with `incident-105`; use exactly `incident-026`, `incident-105`, and `staging-run-104` as the three failures. Add `staging-log-018` as an echo trap, `procedure-123` as time-bounded, and `incident-106` as the same-symptom/different-cause trap. Do not treat the staging failure as the later success. |
| 16 | Remove “2 reversals”. Describe one superseded SQLite decision, one PostgreSQL decision, and a later production-state transition. |
| 17 | Define Strategy X from `incident-034`: exception leaves foreign-key checks disabled and permits orphaned rows. Preserve it as a must-retain high-cost failure. Use 2027-06-30 for corpus-end currentness. |
| 18 | Keep attribution to `adr-007` separate from its derived `runbook-006` restatement. |
| 19 | State that the July 2024 migration succeeded after compatibility mode, shadow reads, and validation. Use `procedure-123` dated 2025-04-15; replace “2026 procedure” with “2025 procedure”. Use the same Strategy X foreign-key restoration prerequisite as Chapter 17. Replace the March locking account with the nine-minute outage in `incident-026` in November 2024. |
| 20 | Give each of the six task families the ledger `as_of` above. Replace the March locking account with the nine-minute outage in `incident-026`; define the importer-index/backfill task and call Strategy X orphaned-row corruption caused by the unmet restoration prerequisite. Add oracle memory and earned-layer ablations without inventing results. |

## Approval checklist

Approved in the preceding review:

- [x] World A IDs and dates from PR #2.
- [x] World B dates and actors; `partner-note-004` says “until the end of Q1 2025”.
- [x] The capstone task and 2024-08-23 cut for the “continue unfinished work” family.
- [x] World C’s overall shape, conditional on the mechanism and fixture corrections in this change.

Pending author approval, recorded only by merge:

- [ ] PR #3 reconciliation facts: `commit-110`, `validation-102`, `commit-117`, `commit-118`, `fixture-scan-109`, `commit-120`, `incident-105`, `staging-run-104`, `staging-log-018`, `incident-106`, `procedure-123`, and all World D artifacts and dates.
- [ ] The corrected `incident-026` outage mechanism.
- [ ] Globally unique display-ID suffixes and the per-family capstone cuts.

The ledger becomes ground truth only after this change is reviewed and merged. Still no corpus generator should be built in this change.
