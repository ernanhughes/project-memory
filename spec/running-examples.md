# Canonical running examples

Status: **PROPOSED — author approval required before generator or fixture work**

This document will be the shared source of truth for the *Memory* manuscript, the controlled corpus, and the Project Memory capstone. Entries marked **RECONCILIATION** choose between contradictory chapter drafts; they are not historical facts and must be approved or replaced by the author.

## World A — event-store migration

### Canonical timeline

| Date | Artifact | Kind | Canonical event |
|---|---|---|---|
| 2024-03-04 | deployment record | state | SQLite is the production event store. |
| 2024-06-14 | `session-014` | evidence | Concurrent-write contention is observed under the target workload. |
| 2024-06-19 | `session-019` | experiment | A controlled benchmark confirms the contention problem. |
| 2024-07-08 | `session-031` | deliberation | The team compares remaining on SQLite with migrating to PostgreSQL. |
| 2024-07-11 | `adr-007` | decision | Move the event store to PostgreSQL. |
| 2024-07-15 | `commit-112` | implementation | Application writes move to PostgreSQL. |
| 2024-07-17 | `session-051` | intention | Backup configuration still targets SQLite and must move before release. |
| 2024-07-22 | deployment record | state | PostgreSQL becomes the production event store. |
| 2024-08-05 | `session-040` | proposal | Redis is proposed for lookup latency. |
| 2024-08-08 | `session-044` | evidence | The working set fits in memory; Redis is judged unnecessary. |
| 2024-08-12 | `adr-009` | decision | Do not introduce Redis. |

**RECONCILIATION:** Use the March → June → July 2024 arc everywhere. Chapter 1’s January decision and April follow-up move later. Chapter 12’s “2023 discussion” becomes the June–July 2024 discussion.

**RECONCILIATION:** `adr-007` is Thursday, 11 July 2024. References to “Friday’s ADR” and “Monday’s ADR” become references to the dated ADR without a weekday.

**RECONCILIATION:** `session-014` is the contention observation, `session-019` the benchmark, and `session-031` the decision discussion. They are related but not interchangeable.

**RECONCILIATION:** The canonical Redis sequence is `session-040` → `session-044` → `adr-009`. The isolated `session-022` reference is retired.

### Canonical decision record

```yaml
event_id: evt-014
kind: decision
topic: event-store backend
content: Move the event store to PostgreSQL.
actors:
  - m.okafor
  - j.lindqvist
decided_at: 2024-07-11
valid_from: 2024-07-22
valid_until: null
supersedes:
  - evt-009
supported_by:
  - evt-011
  - evt-012
source:
  - adr-007
  - session-031
status: current
```

**RECONCILIATION:** The decision date and effective production date are distinct. This preserves the book’s claim that validity may begin when implementation completes rather than when a decision is recorded.

### Open consequences

| Intention | Opened by | Desired state | Canonical status |
|---|---|---|---|
| Move backup configuration to PostgreSQL | `session-051` | Backups target and restore PostgreSQL | unresolved at initial capstone cut |
| Update deployment documentation | migration consequence | Documentation names PostgreSQL | candidate derived loop |
| Review SQLite-specific benchmark fixtures | migration consequence | Fixtures represent the PostgreSQL system | candidate derived loop |
| Tune SQLite performance | earlier work | Improve SQLite contention | superseded by `adr-007` |

The backup obligation is explicit. Documentation and fixture work are derived-loop candidates and must not be labelled as authoritative tasks in E-03/E-04.

## World B — compatibility boundary

| Artifact | Kind | Canonical event |
|---|---|---|
| `adr-013` | decision | Move corpus-import functionality into the corpus domain while retaining a contracted compatibility facade. |
| `issue-088` | task | Migrate live callers to the corpus domain. |
| `issue-089` | task | Remove obsolete internal ownership after caller migration. |
| compatibility contract | constraint | Preserve the facade until the stated compatibility boundary expires. |
| retained regression tests | constraint | Some old-looking references are intentionally retained. |
| documentation note | scoped deferral | Documentation cleanup is deferred, not forgotten. |

This world exists primarily to test correct abstention. A system that reports every old reference as unfinished cleanup fails.

**LEDGER ADDITION NEEDED:** approve dates, actors, and the exact compatibility-expiry condition before World B is rendered.

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

Required scenario classes:

1. repeated episodes where schema-first ordering fails;
2. an independently supported compatibility-first success;
3. an exception where the full sequence is unnecessary;
4. a superficially similar task with a hidden prerequisite;
5. a later environment in which the 2026 procedure is obsolete.

**CONFLICT:** `session-019` currently serves as both the PostgreSQL benchmark and an ordering-pattern episode in manuscript planning. It cannot silently represent two events.

**RECONCILIATION PROPOSAL:** keep `session-019` as the PostgreSQL benchmark and allocate new IDs to the procedure episodes only after author approval.

**LEDGER ADDITIONS NEEDED:** IDs, dates, actors, exact failure mechanism, the nine-minute table-lock event, the strategy-X foreign-key event, and the 2026/2027 obsolescence transition.

## Capstone cut

The first capstone task is:

> Continue the event-store migration and prepare the next safe change.

The evaluated task packet may need to recover:

- the current PostgreSQL decision;
- the rejected Redis proposal;
- the unresolved backup obligation;
- derived documentation and fixture candidates with lower authority;
- the compatibility boundary where relevant;
- the applicable migration procedure, only if later experiments support procedural memory;
- exact provenance for every supplied item.

### Comparison conditions

1. no persistent memory;
2. naive retrieval;
3. the smallest structured system whose preceding experiments returned Type-A.

### Matched controls

- **Memory should matter:** relevant project history changes the correct implementation or restraint.
- **Memory should not matter:** no relevant historical constraint exists, so memory should not change the correct behaviour.

## Approval checklist

Before implementation begins, the author must approve or replace:

- [ ] the March → June → July 2024 migration timeline;
- [ ] the distinct decision and production-effective dates;
- [ ] canonical artifact IDs for contention, benchmark, deliberation, Redis, and backup intention;
- [ ] retirement of `session-022`;
- [ ] World B dates, actors, and compatibility expiry;
- [ ] new artifact IDs for World C;
- [ ] the exact table-lock and foreign-key failure facts;
- [ ] the initial capstone task.

No corpus generator should encode this proposal until the checklist is resolved.
