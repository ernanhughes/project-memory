# Canonical running examples

Status: **REVISED PROPOSAL — unresolved reconciliations require author approval before generator or fixture work**

This document is the shared source of truth for the *Memory* manuscript, the controlled corpus, and the Project Memory capstone. It preserves manuscript facts where they are coherent. Every fact introduced to reconcile conflicting drafts is marked **RECONCILIATION — author to approve**.

## Global time and identifier rules

- The corpus spans **2024-03-01 through 2027-06-30**.
- Every benchmark query has an explicit `as_of` timestamp. If a case omits it, evaluation uses the corpus end, **2027-06-30**, rather than an implicit present.
- Book artifact IDs such as `session-031` and `evt-201` are display labels only. Their numbers do not encode chronology, day of month, scenario, relevance, or authority.
- The future generator must assign separate internal IDs that increase with ingestion order and carry no scenario or date signal. A suitable shape is `gen-000001`. Display IDs remain in artifact content.
- Event IDs use the `evt-2xx` range so they cannot collide numerically with existing `session-0xx` labels.
- Dates below are calendar dates. Where time-of-day affects evaluation, a fixture must state it explicitly.

## World A — event-store migration

### Canonical timeline

| Date | Artifact | Kind | Canonical event |
|---|---|---|---|
| 2024-03-01 (Friday) | `adr-003` / `evt-201` | decision | Use SQLite for the first production event store. |
| 2024-03-04 (Monday) | `deployment-001` / `fact-301` | production state | SQLite becomes the production event store. |
| 2024-05-06 (Monday) | `issue-041` | task | SQLite performance-tuning work opens. **RECONCILIATION — author to approve:** date and display ID. |
| 2024-06-14 (Friday) | `session-014` / `evt-202` | evidence | Concurrent-write contention is observed under the target workload. |
| 2024-06-19 (Wednesday) | `session-019` / `evt-203` | benchmark | A controlled benchmark confirms the contention problem. |
| 2024-06-24 (Monday) | `incident-021` / `evt-204` | incident report | A concurrent importer run fails because of SQLite write contention. **RECONCILIATION — author to approve:** date and incident display ID. |
| 2024-07-08 (Monday) | `session-031` | proposal | m.okafor proposes moving the event store from SQLite to PostgreSQL. |
| 2024-07-09 (Tuesday) | `session-033` | preference | j.lindqvist says, “I still prefer SQLite.” This is neither support for PostgreSQL nor a decision. |
| 2024-07-11 (Thursday) | `adr-007` / `evt-205` | decision | New event-store work should target PostgreSQL. |
| 2024-07-15 (Monday) | `commit-112` | implementation | Application writes are changed to PostgreSQL. |
| 2024-07-17 (Wednesday) | `session-051` / `intent-401` | intention | Backup configuration still targets SQLite and must move before release. |
| 2024-07-22 (Monday) | `deployment-014` / `fact-302` | production state | PostgreSQL becomes the production event store. This deployment is not the release named in `session-051`. |
| 2024-08-05 (Monday) | `session-040` | proposal | Redis is proposed for lookup latency. |
| 2024-08-08 (Thursday) | `session-044` | evidence | The working set fits in memory; Redis is judged unnecessary. |
| 2024-08-12 (Monday) | `adr-009` / `evt-206` | decision | Do not introduce Redis. |
| 2024-08-16 (Friday) | `runbook-006` / `evt-207` | derived restatement | The runbook tells operators to use PostgreSQL, echoing `adr-007`; it is derived evidence, not independent support. **RECONCILIATION — author to approve:** date and runbook display ID. |
| 2024-08-30 (Friday) | `release-024` | release | The first product release after the migration is scheduled. **RECONCILIATION — author to approve:** date and display ID. |
| 2024-10-07 (Monday) | `session-072` | follow-up | A new-service discussion assumes PostgreSQL and supplies the Chapter 1 follow-up. **RECONCILIATION — author to approve:** date and display ID. |

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
decided_at: 2024-03-01
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
decided_at: 2024-07-11
valid_from: 2024-07-22
valid_until: null
supersedes:
  - fact-301
supported_by:
  - deployment-014
source:
  - deployment-014
status: current
```

At `as_of: 2024-07-15`, “What should new code target?” resolves to PostgreSQL, while “What runs in production?” resolves to SQLite. At and after 2024-07-22, the production-state answer is PostgreSQL.

### Provenance fixtures and legacy event mapping

| Old manuscript event | Canonical event | Source artifact | Date | Role |
|---|---|---|---|---|
| `evt-009` | `evt-201` | `adr-003` | 2024-03-01 | Earlier SQLite decision, superseded by `evt-205`. |
| `evt-011` | `evt-203` | `session-019` | 2024-06-19 | Benchmark evidence supporting migration. |
| `evt-012` | `evt-204` | `incident-021` | 2024-06-24 | Incident evidence supporting migration. |
| none | `evt-207` | `runbook-006` | 2024-08-16 | Derived echo of `adr-007`, not independent support. |

The old `evt-009`, `evt-011`, `evt-012`, and `evt-014` labels must not survive in regenerated fixtures. This prevents the `evt-014` / `session-014` collision.

### Intentions and release boundary

| Intention | Opened | Deadline | Desired state | Canonical status |
|---|---|---|---|---|
| Move backup configuration to PostgreSQL | `session-051`, 2024-07-17 | before `release-024`, 2024-08-30 | Backups target and restore PostgreSQL | unresolved at initial capstone cut |
| Update deployment documentation | migration consequence | none recorded | Documentation names PostgreSQL | candidate derived loop |
| Review SQLite-specific benchmark fixtures | migration consequence | none recorded | Fixtures represent the PostgreSQL system | candidate derived loop |
| Tune SQLite performance | `issue-041`, 2024-05-06 | none recorded | Improve SQLite contention | superseded by `evt-205` |

The initial capstone cut is `as_of: 2024-08-23`, one week before `release-024`. Thus the explicit backup obligation is still open and has not silently missed its deadline. The 22 July production deployment is not the release referred to by `session-051`.

Documentation and fixture work are derived-loop candidates. They must not be labelled as authoritative tasks in E-03/E-04.

## World B — compatibility boundary

The following entries are proposals needed to make the Chapter 11 narrative executable. **Every entry in this section is RECONCILIATION — author to approve.** They do not replace Chapter 11 silently.

| Date | Artifact | Actor(s) | Kind | Proposed canonical event |
|---|---|---|---|---|
| 2025-01-13 | `adr-013` | a.silva, m.okafor | decision | Remove the legacy `corpus_import` domain. Keep a compatibility facade only for the external partner commitment. |
| 2025-01-14 | `issue-088` | a.silva | task | Migrate CLI callers away from `corpus_import`. |
| 2025-01-14 | `issue-089` | m.okafor | task | Migrate web callers away from `corpus_import`. |
| 2025-01-16 | `partner-note-004` | j.lindqvist | constraint | Preserve the partner-facing facade “until Q1”. Proposed interpretation: through 2025-03-31 inclusive. |
| 2025-01-22 | `issue-088` | a.silva | outcome | CLI caller migration completes. |
| 2025-01-29 | `issue-089` | m.okafor | outcome | Web caller migration completes. |
| 2025-01-30 | `tests-compat-003` | a.silva | constraint | Regression tests for the partner facade remain intentionally. |
| 2025-01-31 | `docs-note-012` | m.okafor | scoped deferral | Documentation cleanup is deferred; it is not an open caller-migration task. |

This preserves Chapter 11’s distinction:

- `adr-013` removes the legacy domain; it does not move the domain wholesale behind a facade.
- `issue-088` and `issue-089` migrate CLI and web callers respectively.
- The compatibility facade exists for the partner commitment, “until Q1”.
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

All exact dates, actors, and display IDs below are **RECONCILIATION — author to approve** unless already present in the manuscript.

| Date | Artifact | Actor(s) | Scenario role | Canonical event |
|---|---|---|---|---|
| 2024-11-14 | `incident-026` | m.okafor | failure episode | Applying a PostgreSQL schema change before compatibility code causes a nine-minute table lock. |
| 2025-02-11 | `session-083` | a.silva | failure episode | A second schema-first attempt breaks a live caller before compatibility behaviour is available. |
| 2025-04-03 | `staging-log-017` | j.lindqvist | independent support | Compatibility-first ordering succeeds in staging, including shadow reads and validation. |
| 2025-04-10 | `run-021` | j.lindqvist | success outcome | The compatibility-first production migration completes without the earlier failure mode. |
| 2025-06-18 | `incident-034` | a.silva | hidden prerequisite | Strategy X fails because a foreign-key prerequisite was not satisfied. |
| 2026-02-10 | `change-061` | m.okafor | exception | A small additive migration is safe without the full breaking-change sequence. |
| 2027-03-15 | `platform-note-009` | j.lindqvist | procedure obsolescence | A platform change removes the assumptions on which the 2026 procedure depends. |
| 2027-06-30 | corpus boundary | evaluator | end state | The corpus closes; unresolved current claims are evaluated at this date unless a query supplies another `as_of`. |

`session-019` remains the World A PostgreSQL benchmark. It is not reused for a World C ordering-pattern episode.

The former “March table-lock” references in Chapters 12, 19, and 20 must point to `incident-026` on 2024-11-14. In March 2024, production still ran SQLite.

## Capstone cut

The initial capstone task, evaluated at `as_of: 2024-08-23`, is:

> Continue the event-store migration and prepare the next safe change.

The task packet may need to recover:

- the current PostgreSQL target decision;
- the still-current PostgreSQL production-state fact;
- the rejected Redis proposal;
- the unresolved backup obligation and its release deadline;
- derived documentation and fixture candidates with lower authority;
- the compatibility boundary where a later task makes it relevant;
- the applicable migration procedure, only if preceding experiments support procedural memory;
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

These are manuscript edits required to make the book match this ledger. Exact wording can follow each chapter’s voice, but the named facts must not change.

| Chapter | Required edits |
|---|---|
| 1 | Replace the January migration decision with `adr-007` on 2024-07-11. Replace the April follow-up with the October 2024 follow-up represented by `session-072`. |
| 2 | Replace old `evt-009/011/012/014` fixture IDs with `evt-201/203/204/205`. Keep `session-031` as the proposal source and distinguish the 11 July decision from the 22 July production state. |
| 3 | Retire `session-022`. Use `session-040`, `session-044`, and `adr-009` for Redis. Use `session-014` only for the contention observation. |
| 4 | Restore the full trap: Monday `session-031` proposal, Tuesday `session-033` SQLite preference, Thursday `adr-007` decision. Do not call `session-031` generic deliberation. |
| 5 | Use the same three-part Chapter 4 sequence. Replace “Friday’s ADR” with the dated Thursday decision. |
| 6 | Where the example depends on authority, keep proposals, preferences, and decisions as separate candidate passages. |
| 7 | Replace the “January stress test” with the 2024-06-19 benchmark and the “March importer incident” with the 2024-06-24 incident. Add `session-033` as a non-supporting distractor and `runbook-006` as a derived echo, not independent support. |
| 8 | Preserve the March → June → July arc. State explicitly that the PostgreSQL target decision is current from 11 July while PostgreSQL production state begins 22 July. |
| 9 | Replace any Monday description of `adr-007` with Thursday or omit the weekday. Date the SQLite tuning task to 2024-05-06. Tie “before release” to proposed `release-024` on 2024-08-30, not the 22 July deployment. |
| 10 | Use the explicit backup obligation from `session-051`; keep documentation and fixture work labelled as derived-loop candidates. |
| 11 | Restore Chapter 11 semantics: `adr-013` removes the legacy domain; `issue-088` migrates CLI callers; `issue-089` migrates web callers; the partner facade remains “until Q1”. Apply proposed dates and actors only after approval. |
| 12 | Change the “2023” PostgreSQL discussion to June–July 2024. Replace the “March” PostgreSQL table lock with `incident-026` on 2024-11-14. |
| 13 | Keep decision retrieval separate from production-state retrieval and require explicit `as_of` values. |
| 14 | Preserve source distinctions so a runbook echo cannot count as independent support for `adr-007`. |
| 15 | Do not consolidate `session-031`, `session-033`, and `adr-007` into one undifferentiated migration claim. |
| 16 | Remove the unsupported “2 reversals” statement. Describe one superseded SQLite decision, one PostgreSQL decision, and a later production-state transition instead. |
| 17 | Use the corpus end 2027-06-30 when discussing whether an open-ended claim is current. |
| 18 | Keep attribution to `adr-007` separate from its derived `runbook-006` restatement. |
| 19 | Replace the “March” table lock with `incident-026` on 2024-11-14. Keep the additive-migration exception and 2027 obsolescence case separate from the core procedure. |
| 20 | Replace the “March” table lock with `incident-026` on 2024-11-14. Add oracle memory as the fourth condition and per-layer ablations; report captured oracle gap without inventing results. |

## Approval checklist

Approved from review:

- [x] March → June → July 2024 arc.
- [x] SQLite tuning task opens in May 2024.
- [x] Chapter 1 follow-up moves to October 2024.
- [x] Corpus end is 2027-06-30.
- [x] Decision and production state are distinct records.
- [x] `session-033` is restored as the Q2 preference trap.
- [x] Book IDs are display labels; generator IDs are time-monotonic and uncorrelated with scenario or date.
- [x] Event IDs are renumbered to avoid session/event numeric collisions.
- [x] `session-022` is retired.
- [x] The 22 July deployment is not the release named by `session-051`.
- [x] `incident-026` moves after July 2024 and the contradictory “March” references are listed for correction.
- [x] The capstone adds oracle memory and per-layer ablations.

Still requiring author approval because exact facts were introduced as reconciliation:

- [ ] `issue-041`, `incident-021`, `runbook-006`, `release-024`, and `session-072` display IDs and exact dates.
- [ ] World B dates, actors, the exact `adr-013` wording, and whether “until Q1” means through 2025-03-31 inclusive.
- [ ] World C dates, actors, new display IDs, and exact failure mechanisms.
- [ ] The initial capstone task and its 2024-08-23 cut.

No corpus generator should encode unresolved reconciliation proposals until this checklist is approved or edited.
