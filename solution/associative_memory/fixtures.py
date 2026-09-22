"""The deterministic ledger graph, and the cue set that probes it.

Before requiring LLM-extracted GraphRAG output, the chapter needs a graph
small enough to reason about and fixed enough to re-run. This module
builds one directly from the project's canonical running examples, so
every node and edge corresponds to an artifact the rest of the book
already uses. No identifier or date here is invented.

The graph is not friendly. It contains, on purpose:

* a dominant hub (the event-store migration touches nearly everything);
* derived echoes that restate a decision without independently supporting
  it (`runbook-006`, `staging-log-018`);
* a same-symptom, different-cause trap (`incident-106` against
  `incident-026`);
* a superseded procedure (`procedure-123` after `platform-note-125`);
* weakly connected truths (`fixture-scan-109`, `commit-120`);
* three actors who each appear in three unrelated regions of the graph;
* cycles, because real derived graphs have them.

An associative mechanism that only wins on a corpus of tidy chains has
not been tested.
"""

from __future__ import annotations

import json
from pathlib import Path

from .graph.adapter import CLAIM, ENTITY, SOURCE, MemoryEdge, MemoryGraph, MemoryNode

GRAPH_VERSION = "assoc-ledger-v0.1"
CORPUS_VERSION = "running-examples-2026-09"
CUE_SET_VERSION = "assoc-cues-v0.1"

# (artifact id, kind label, date, description)
ARTIFACTS: tuple[tuple[str, str, str, str], ...] = (
    # World A — event-store migration
    ("adr-003", "decision-record", "2024-03-01",
     "Decision to use SQLite for the first production event store."),
    ("deployment-001", "deployment", "2024-03-04",
     "SQLite becomes the production event store."),
    ("issue-041", "issue", "2024-05-06",
     "SQLite performance-tuning work opens."),
    ("session-014", "session", "2024-06-14",
     "Concurrent-write contention observed under the target workload."),
    ("session-019", "session", "2024-06-19",
     "Controlled benchmark confirms the write-contention problem."),
    ("incident-021", "incident", "2024-06-24",
     "A concurrent importer run fails because of SQLite write contention."),
    ("session-031", "session", "2024-07-08",
     "a.silva proposes moving the event store from SQLite to PostgreSQL."),
    ("session-033", "session", "2024-07-09",
     "j.lindqvist states a personal preference for staying on SQLite."),
    ("adr-007", "decision-record", "2024-07-11",
     "New event-store work should target PostgreSQL."),
    ("commit-110", "commit", "2024-07-15",
     "Compatibility mode enabled on the migration branch and in staging."),
    ("commit-112", "commit", "2024-07-15",
     "Application writes changed to PostgreSQL and exercised in staging."),
    ("session-051", "session", "2024-07-17",
     "Backup configuration still targets SQLite and must move before the "
     "release."),
    ("validation-102", "validation", "2024-07-19",
     "Staging shadow reads from both backends agree; migration cleared."),
    ("deployment-101", "deployment", "2024-07-22",
     "PostgreSQL becomes the production event store."),
    ("migration-run-103", "migration-run", "2024-07-22",
     "The event-store migration succeeds after compatibility mode, schema "
     "change, shadow reads, and validation."),
    ("fixture-scan-109", "scan", "2024-07-23",
     "Benchmark fixtures still encode SQLite timing and locking assumptions."),
    ("session-040", "session", "2024-08-05",
     "Redis is proposed for lookup latency."),
    ("session-044", "session", "2024-08-08",
     "The working set fits in memory; Redis is judged unnecessary."),
    ("adr-009", "decision-record", "2024-08-12",
     "Do not introduce Redis."),
    ("runbook-006", "runbook", "2024-08-16",
     "Operator runbook tells operators to use PostgreSQL, echoing adr-007."),
    ("commit-117", "commit", "2024-08-21",
     "A commit titled refresh deploy docs updates deployment documentation."),
    ("commit-118", "commit", "2024-08-27",
     "Backup configuration and its restore check move to PostgreSQL."),
    ("release-024", "release", "2024-08-30",
     "The first product release after the migration ships."),
    ("commit-120", "commit", "2024-09-03",
     "PostgreSQL-aware benchmark fixtures replace SQLite-dependent "
     "assumptions."),
    ("session-072", "session", "2024-10-07",
     "A new-service discussion assumes PostgreSQL."),
    # World B — compatibility boundary
    ("adr-013", "decision-record", "2025-01-13",
     "Remove the legacy corpus_import domain, keeping a compatibility "
     "facade for the external partner commitment."),
    ("issue-088", "issue", "2025-01-14",
     "Migrate CLI callers away from corpus_import."),
    ("issue-089", "issue", "2025-01-14",
     "Migrate web callers away from corpus_import."),
    ("partner-note-004", "constraint", "2025-01-16",
     "Preserve the partner-facing facade until the end of Q1 2025."),
    ("tests-compat-122", "constraint", "2025-01-30",
     "Regression tests for the partner facade remain intentionally."),
    ("docs-note-012", "deferral", "2025-01-31",
     "Documentation cleanup is deferred; it is not an open migration task."),
    # World C — migration procedure
    ("incident-026", "incident", "2024-11-14",
     "A schema-first migration drops a column live code still reads, "
     "causing a nine-minute outage until rollback."),
    ("staging-log-018", "log", "2024-11-18",
     "A staging log restating incident-026; it adds no independent episode."),
    ("incident-105", "incident", "2025-02-11",
     "A schema-first migration breaks a live caller before compatibility "
     "behaviour is available."),
    ("staging-run-104", "staging-run", "2025-03-20",
     "A schema-first staging migration invalidates the old reader before "
     "the compatibility path is deployed."),
    ("run-124", "migration-run", "2025-04-10",
     "A compatibility-first production migration completes with shadow "
     "reads and validation."),
    ("procedure-123", "procedure", "2025-04-15",
     "The compatibility-first sequence is recorded as the project procedure "
     "for breaking schema migrations."),
    ("incident-034", "incident", "2025-06-18",
     "Strategy X disables foreign-key checks before copying rows and fails "
     "to restore them after an exception, permitting orphaned rows."),
    ("incident-106", "incident", "2025-08-12",
     "A nine-minute-looking timeout caused by network saturation, not "
     "schema ordering."),
    ("change-061", "change", "2026-02-10",
     "A small additive migration is safe without the full breaking-change "
     "sequence."),
    ("platform-note-125", "supersession", "2027-03-15",
     "A platform change removes the assumptions behind procedure-123."),
    # World D — dated task and context fixtures
    ("benchmark-128", "benchmark", "2024-04-18",
     "An early SQLite-only importer throughput baseline."),
    ("policy-129", "policy", "2024-09-06",
     "All schema migrations must be reversible with a passing rollback "
     "test."),
    ("requirement-127", "requirement", "2024-09-12",
     "The importer must accept the v1 event representation until "
     "2025-06-30."),
    ("benchmark-126", "benchmark", "2024-11-25",
     "The PostgreSQL importer baseline supersedes benchmark-128."),
    ("release-121", "release", "2025-02-14",
     "The later compatibility release ships."),
)

# (entity id, label, description, terms)
ENTITIES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("a.silva", "a.silva", "Engineer on the event-store migration, the "
     "corpus_import removal, and the Strategy X backfill failure.",
     ("silva", "engineer")),
    ("j.lindqvist", "j.lindqvist", "Engineer who preferred SQLite, holds the "
     "partner facade commitment, and recorded the migration procedure.",
     ("lindqvist", "engineer")),
    ("m.okafor", "m.okafor", "Engineer on event-store decisions, production "
     "deployments, and the web caller migration.",
     ("okafor", "engineer")),
    ("sqlite", "SQLite", "The original event-store backend, superseded for "
     "new work.", ("sqlite", "backend", "database")),
    ("postgresql", "PostgreSQL", "The current event-store backend.",
     ("postgresql", "postgres", "backend", "database")),
    ("redis", "Redis", "A lookup cache that was proposed and rejected.",
     ("redis", "cache", "lookup", "latency")),
    ("event-store", "event store", "The event-store subsystem and its "
     "backend choice.", ("event", "store", "backend")),
    ("backup-configuration", "backup configuration", "Backup targets and "
     "restore checks for the event store.",
     ("backup", "restore", "configuration")),
    ("deployment-documentation", "deployment documentation",
     "Documentation describing how the system is deployed.",
     ("deployment", "documentation", "docs")),
    ("benchmark-fixtures", "benchmark fixtures", "Test fixtures encoding "
     "backend timing and locking assumptions.",
     ("benchmark", "fixtures", "timing", "locking")),
    ("corpus_import", "corpus_import", "The legacy import domain removed in "
     "2025.", ("corpus_import", "legacy", "domain", "callers")),
    ("partner-facade", "partner facade", "The compatibility facade preserved "
     "for an external partner commitment.",
     ("partner", "facade", "compatibility", "commitment")),
    ("schema-migration", "schema migration", "Breaking schema changes and "
     "the order in which they are applied.",
     ("schema", "migration", "breaking", "ordering")),
    ("strategy-x", "Strategy X", "A backfill strategy that disables foreign "
     "key checks while copying rows.",
     ("strategy", "backfill", "copying")),
    ("foreign-key-checks", "foreign-key checks", "Referential integrity "
     "checks that must be restored after a backfill.",
     ("foreign", "key", "integrity", "orphaned")),
    ("importer", "importer", "The corpus importer and its throughput "
     "baselines.", ("importer", "throughput", "import")),
    ("release", "release", "Product releases that gate outstanding work.",
     ("release", "ship", "deadline")),
)

# (claim id, label, description, source artifacts)
CLAIMS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("evt-201", "SQLite decision", "Use SQLite for the first production "
     "event store.", ("adr-003",)),
    ("evt-202", "contention evidence", "Concurrent-write contention is "
     "observed under the target workload.", ("session-014",)),
    ("evt-203", "benchmark evidence", "A controlled benchmark confirms the "
     "contention problem.", ("session-019",)),
    ("evt-204", "incident evidence", "A concurrent importer run fails "
     "because of write contention.", ("incident-021",)),
    ("evt-205", "PostgreSQL decision", "New event-store work should target "
     "PostgreSQL.", ("adr-007",)),
    ("evt-206", "Redis decision", "Do not introduce Redis.", ("adr-009",)),
    ("evt-207", "runbook restatement", "The runbook restates the PostgreSQL "
     "target for operators.", ("runbook-006",)),
    ("fact-301", "SQLite in production", "SQLite runs in production, from "
     "March to July 2024.", ("deployment-001",)),
    ("fact-302", "PostgreSQL in production", "PostgreSQL runs in production "
     "from July 2024.", ("deployment-101",)),
    ("intent-401", "backup obligation", "Backup configuration must move to "
     "PostgreSQL before the release.", ("session-051",)),
)

# (edge id, source, target, relation, association, evidence confidence,
#  source artifacts, description, bidirectional)
RELATIONS: tuple[tuple, ...] = (
    # --- World A: the decision spine -----------------------------------
    ("e001", "claim:evt-205", "source:adr-007", "RECORDED_IN", 0.85, 0.95,
     ("adr-007",), "The PostgreSQL event-store decision as recorded", True),
    ("e002", "claim:evt-205", "claim:evt-202", "SUPPORTED_BY", 0.8, 0.85,
     ("session-014",), "Write contention evidence supporting the backend "
     "decision", True),
    ("e003", "claim:evt-205", "claim:evt-203", "SUPPORTED_BY", 0.8, 0.9,
     ("session-019",), "Benchmark evidence supporting the backend decision",
     True),
    ("e004", "claim:evt-205", "claim:evt-204", "SUPPORTED_BY", 0.8, 0.9,
     ("incident-021",), "Incident evidence supporting the backend decision",
     True),
    ("e005", "claim:evt-205", "claim:evt-201", "SUPERSEDES", 0.6, 0.95,
     ("adr-007", "adr-003"), "The PostgreSQL decision supersedes the earlier "
     "SQLite decision", True),
    ("e006", "claim:evt-202", "source:session-014", "RECORDED_IN", 0.7, 0.9,
     ("session-014",), "Contention observation session", True),
    ("e007", "claim:evt-203", "source:session-019", "RECORDED_IN", 0.7, 0.9,
     ("session-019",), "Benchmark session confirming contention", True),
    ("e008", "claim:evt-204", "source:incident-021", "RECORDED_IN", 0.7, 0.9,
     ("incident-021",), "Importer failure incident report", True),
    ("e009", "claim:evt-201", "source:adr-003", "RECORDED_IN", 0.6, 0.9,
     ("adr-003",), "The original SQLite decision record", True),
    ("e010", "entity:event-store", "claim:evt-205", "SUBJECT_OF", 0.75, 0.9,
     ("adr-007",), "Event-store backend target decision", True),
    ("e011", "entity:event-store", "claim:evt-201", "SUBJECT_OF", 0.5, 0.9,
     ("adr-003",), "Event-store backend original choice", True),
    ("e012", "entity:postgresql", "claim:evt-205", "NAMED_IN", 0.8, 0.9,
     ("adr-007",), "PostgreSQL named as the event-store target", True),
    ("e013", "entity:sqlite", "claim:evt-201", "NAMED_IN", 0.6, 0.9,
     ("adr-003",), "SQLite named as the original backend", True),
    ("e014", "entity:sqlite", "claim:evt-202", "IMPLICATED_IN", 0.55, 0.8,
     ("session-014",), "SQLite write contention under concurrency", True),
    # proposal, preference, decision: three different speech acts
    ("e015", "source:session-031", "claim:evt-205", "PROPOSED", 0.5, 0.4,
     ("session-031",), "a.silva proposes the PostgreSQL move; a proposal is "
     "not a decision", True),
    ("e016", "source:session-033", "entity:sqlite", "PREFERRED", 0.35, 0.3,
     ("session-033",), "j.lindqvist states a personal preference for SQLite; "
     "a preference is not support", True),
    # production state, separate from the decision
    ("e017", "claim:fact-302", "source:deployment-101", "RECORDED_IN", 0.8,
     0.95, ("deployment-101",), "PostgreSQL production deployment", True),
    ("e018", "claim:fact-301", "source:deployment-001", "RECORDED_IN", 0.6,
     0.95, ("deployment-001",), "SQLite production deployment", True),
    ("e019", "claim:fact-302", "claim:fact-301", "SUPERSEDES", 0.6, 0.95,
     ("deployment-101",), "Production backend state transition", True),
    ("e020", "entity:event-store", "claim:fact-302", "SUBJECT_OF", 0.7, 0.9,
     ("deployment-101",), "Current production event-store backend", True),
    # migration implementation chain
    ("e021", "claim:evt-205", "source:commit-110", "IMPLEMENTED_BY", 0.6, 0.8,
     ("commit-110",), "Compatibility mode enabled on the migration branch",
     True),
    ("e022", "source:commit-110", "source:commit-112", "PRECEDES", 0.65, 0.85,
     ("commit-110", "commit-112"), "Compatibility before the write-path "
     "change", True),
    ("e023", "source:commit-112", "source:validation-102", "PRECEDES", 0.6,
     0.85, ("commit-112", "validation-102"), "Staging writes before shadow "
     "read validation", True),
    ("e024", "source:validation-102", "source:deployment-101", "CLEARED", 0.6,
     0.85, ("validation-102",), "Validation clears the production migration",
     True),
    ("e025", "source:migration-run-103", "source:deployment-101",
     "DESCRIBES", 0.6, 0.85, ("migration-run-103",),
     "The successful migration episode", True),
    # the backup obligation: reachable only through the migration
    ("e026", "source:commit-112", "claim:intent-401", "RAISED", 0.6, 0.7,
     ("session-051",), "The staged write-path change leaves backup "
     "configuration behind", True),
    ("e027", "claim:intent-401", "source:session-051", "RECORDED_IN", 0.7,
     0.9, ("session-051",), "Backup configuration obligation before the "
     "release", True),
    ("e028", "claim:intent-401", "entity:backup-configuration", "ABOUT", 0.7,
     0.9, ("session-051",), "Backup targets and restore checks", True),
    ("e029", "claim:intent-401", "source:commit-118", "COMPLETED_BY", 0.7,
     0.85, ("commit-118",), "Backup configuration and restore check moved to "
     "PostgreSQL", True),
    ("e030", "claim:intent-401", "source:release-024", "DUE_BEFORE", 0.6, 0.8,
     ("session-051", "release-024"), "The obligation is due before the first "
     "post-migration release", True),
    ("e031", "source:release-024", "entity:release", "INSTANCE_OF", 0.5, 0.9,
     ("release-024",), "The first release after the migration", True),
    # silent completion and derived loops: weakly linked truths
    ("e032", "entity:deployment-documentation", "source:commit-117",
     "COMPLETED_BY", 0.4, 0.6, ("commit-117",),
     "Deploy documentation refreshed without linking to the obligation",
     True),
    ("e033", "claim:evt-205", "entity:deployment-documentation",
     "CONSEQUENCE_FOR", 0.35, 0.5, ("adr-007",),
     "The backend decision implies documentation work", True),
    ("e034", "claim:evt-205", "entity:benchmark-fixtures", "CONSEQUENCE_FOR",
     0.3, 0.5, ("adr-007",), "The backend decision implies fixture review",
     True),
    ("e035", "entity:benchmark-fixtures", "source:fixture-scan-109",
     "STATE_OBSERVED_IN", 0.45, 0.8, ("fixture-scan-109",),
     "Fixtures still encode SQLite timing and locking assumptions", True),
    ("e036", "entity:benchmark-fixtures", "source:commit-120",
     "COMPLETED_BY", 0.45, 0.85, ("commit-120",),
     "PostgreSQL-aware benchmark fixtures replace the old assumptions",
     True),
    # the derived echo: restates a decision without supporting it
    ("e037", "claim:evt-207", "claim:evt-205", "DERIVED_FROM", 0.3, 0.2,
     ("runbook-006",), "The runbook echoes the decision; it is derived "
     "evidence, not independent support", True),
    ("e038", "claim:evt-207", "source:runbook-006", "RECORDED_IN", 0.5, 0.9,
     ("runbook-006",), "Operator runbook naming PostgreSQL", True),
    # Redis: a separate decision region
    ("e039", "claim:evt-206", "source:adr-009", "RECORDED_IN", 0.8, 0.95,
     ("adr-009",), "The decision not to introduce Redis", True),
    ("e040", "claim:evt-206", "source:session-044", "SUPPORTED_BY", 0.75, 0.9,
     ("session-044",), "The working set fits in memory, so a lookup cache is "
     "unnecessary", True),
    ("e041", "source:session-040", "claim:evt-206", "PROPOSED", 0.5, 0.4,
     ("session-040",), "Redis proposed for lookup latency", True),
    ("e042", "entity:redis", "claim:evt-206", "SUBJECT_OF", 0.8, 0.9,
     ("adr-009",), "Redis lookup cache decision", True),
    ("e043", "entity:event-store", "entity:redis", "PROPOSED_FOR", 0.3, 0.6,
     ("session-040",), "A lookup cache was proposed in front of the event "
     "store", True),
    # SQLite tuning: superseded work
    ("e044", "entity:sqlite", "source:issue-041", "TUNING_TASK", 0.35, 0.8,
     ("issue-041",), "SQLite performance tuning work", True),
    ("e045", "source:issue-041", "claim:evt-205", "SUPERSEDED_BY", 0.4, 0.8,
     ("adr-007",), "Tuning the old backend is superseded by the migration",
     True),
    ("e046", "source:session-072", "entity:postgresql", "ASSUMES", 0.4, 0.7,
     ("session-072",), "A new-service discussion assumes PostgreSQL", True),
    # --- actors: the same person across unrelated regions ---------------
    ("e047", "entity:a.silva", "source:session-031", "AUTHORED", 0.45, 0.9,
     ("session-031",), "a.silva proposes the event-store move to PostgreSQL",
     True),
    ("e048", "entity:a.silva", "source:adr-013", "DECIDED", 0.45, 0.9,
     ("adr-013",), "a.silva on the corpus_import removal decision", True),
    ("e049", "entity:a.silva", "source:issue-088", "ASSIGNED", 0.45, 0.9,
     ("issue-088",), "a.silva migrates CLI callers away from corpus_import",
     True),
    ("e050", "entity:a.silva", "source:incident-034", "REPORTED", 0.45, 0.9,
     ("incident-034",), "a.silva reports the Strategy X foreign-key failure",
     True),
    ("e051", "entity:a.silva", "source:incident-105", "REPORTED", 0.4, 0.9,
     ("incident-105",), "a.silva reports a schema-first migration failure",
     True),
    ("e052", "entity:a.silva", "source:tests-compat-122", "AUTHORED", 0.35,
     0.85, ("tests-compat-122",), "a.silva retains partner facade regression "
     "tests", True),
    ("e053", "entity:a.silva", "source:migration-run-103", "RAN", 0.4, 0.85,
     ("migration-run-103",), "a.silva on the successful event-store "
     "migration run", True),
    ("e054", "entity:j.lindqvist", "source:session-033", "AUTHORED", 0.45,
     0.9, ("session-033",), "j.lindqvist prefers SQLite for the event store",
     True),
    ("e055", "entity:j.lindqvist", "source:adr-007", "DECIDED", 0.45, 0.9,
     ("adr-007",), "j.lindqvist co-decides the PostgreSQL event-store "
     "target", True),
    ("e056", "entity:j.lindqvist", "source:partner-note-004", "AUTHORED",
     0.5, 0.9, ("partner-note-004",), "j.lindqvist records the partner "
     "facade commitment", True),
    ("e057", "entity:j.lindqvist", "source:procedure-123", "AUTHORED", 0.5,
     0.9, ("procedure-123",), "j.lindqvist records the compatibility-first "
     "schema migration procedure", True),
    ("e058", "entity:j.lindqvist", "source:run-124", "RAN", 0.4, 0.85,
     ("run-124",), "j.lindqvist runs the compatibility-first production "
     "migration", True),
    ("e059", "entity:j.lindqvist", "source:staging-run-104", "RAN", 0.4, 0.85,
     ("staging-run-104",), "j.lindqvist hits a schema-first staging failure",
     True),
    ("e060", "entity:m.okafor", "source:adr-007", "DECIDED", 0.45, 0.9,
     ("adr-007",), "m.okafor co-decides the PostgreSQL event-store target",
     True),
    ("e061", "entity:m.okafor", "source:deployment-101", "DEPLOYED", 0.45,
     0.9, ("deployment-101",), "m.okafor deploys PostgreSQL to production",
     True),
    ("e062", "entity:m.okafor", "source:issue-089", "ASSIGNED", 0.45, 0.9,
     ("issue-089",), "m.okafor migrates web callers away from corpus_import",
     True),
    ("e063", "entity:m.okafor", "source:incident-026", "REPORTED", 0.45, 0.9,
     ("incident-026",), "m.okafor reports the nine-minute schema outage",
     True),
    ("e064", "entity:m.okafor", "source:docs-note-012", "AUTHORED", 0.35,
     0.85, ("docs-note-012",), "m.okafor defers corpus_import documentation "
     "cleanup", True),
    ("e065", "entity:m.okafor", "source:change-061", "AUTHORED", 0.35, 0.85,
     ("change-061",), "m.okafor records an additive migration exception",
     True),
    # --- World B: the compatibility boundary -----------------------------
    ("e066", "entity:corpus_import", "source:adr-013", "REMOVED_BY", 0.8,
     0.9, ("adr-013",), "The legacy corpus_import domain is removed", True),
    ("e067", "source:adr-013", "source:issue-088", "SPAWNED", 0.7, 0.85,
     ("adr-013", "issue-088"), "CLI caller migration away from "
     "corpus_import", True),
    ("e068", "source:adr-013", "source:issue-089", "SPAWNED", 0.7, 0.85,
     ("adr-013", "issue-089"), "Web caller migration away from "
     "corpus_import", True),
    ("e069", "entity:partner-facade", "source:adr-013", "PRESERVED_BY", 0.7,
     0.85, ("adr-013",), "A compatibility facade is kept for the partner "
     "commitment", True),
    ("e070", "entity:partner-facade", "source:partner-note-004",
     "CONSTRAINED_BY", 0.8, 0.9, ("partner-note-004",),
     "The partner commitment preserves the facade until the end of Q1 2025",
     True),
    ("e071", "entity:partner-facade", "source:tests-compat-122",
     "PROTECTED_BY", 0.6, 0.85, ("tests-compat-122",),
     "Regression tests for the partner facade remain intentionally", True),
    ("e072", "entity:corpus_import", "source:docs-note-012", "DEFERRED_WORK",
     0.4, 0.8, ("docs-note-012",), "Documentation cleanup deferred; not an "
     "open migration task", True),
    ("e073", "source:release-121", "entity:partner-facade", "SHIPPED_WITH",
     0.4, 0.75, ("release-121",), "The later compatibility release ships "
     "with the facade", True),
    # --- World C: the migration procedure --------------------------------
    ("e074", "entity:schema-migration", "source:incident-026", "FAILED_IN",
     0.7, 0.9, ("incident-026",), "A schema-first migration drops a live "
     "column, causing a nine-minute outage", True),
    ("e075", "entity:schema-migration", "source:incident-105", "FAILED_IN",
     0.7, 0.9, ("incident-105",), "A schema-first migration breaks a live "
     "caller", True),
    ("e076", "entity:schema-migration", "source:staging-run-104", "FAILED_IN",
     0.65, 0.85, ("staging-run-104",), "A schema-first staging migration "
     "invalidates the old reader", True),
    ("e077", "source:staging-log-018", "source:incident-026", "ECHOES", 0.3,
     0.2, ("staging-log-018",), "A staging log restating the outage; it is "
     "not an independent failure episode", True),
    ("e078", "source:procedure-123", "source:incident-026", "LEARNED_FROM",
     0.6, 0.85, ("procedure-123",), "The compatibility-first procedure "
     "learns from the schema-first outage", True),
    ("e079", "source:procedure-123", "source:run-124", "VALIDATED_BY", 0.6,
     0.85, ("run-124",), "A compatibility-first migration completes with "
     "shadow reads and validation", True),
    ("e080", "entity:schema-migration", "source:procedure-123",
     "PROCEDURE_FOR", 0.75, 0.9, ("procedure-123",),
     "The recorded procedure for breaking schema migrations", True),
    ("e081", "source:platform-note-125", "source:procedure-123",
     "SUPERSEDES", 0.6, 0.9, ("platform-note-125",),
     "A platform change removes the assumptions behind the procedure", True),
    ("e082", "source:change-061", "source:procedure-123", "EXCEPTION_TO",
     0.4, 0.8, ("change-061",), "A small additive migration is safe without "
     "the full sequence", True),
    ("e083", "source:incident-106", "source:incident-026", "RESEMBLES", 0.45,
     0.15, ("incident-106",), "A nine-minute-looking timeout with the same "
     "symptom and a different cause", True),
    ("e084", "entity:strategy-x", "source:incident-034", "FAILED_IN", 0.75,
     0.9, ("incident-034",), "Strategy X permits orphaned rows after an "
     "exception", True),
    ("e085", "entity:strategy-x", "entity:foreign-key-checks", "DISABLES",
     0.7, 0.9, ("incident-034",), "Strategy X disables foreign-key checks "
     "while copying rows", True),
    ("e086", "entity:foreign-key-checks", "source:incident-034",
     "NOT_RESTORED_IN", 0.7, 0.9, ("incident-034",),
     "Foreign-key checks are not restored after the exception, permitting "
     "orphaned rows", True),
    ("e087", "entity:strategy-x", "entity:importer", "USED_BY", 0.4, 0.7,
     ("incident-034",), "The importer backfill uses Strategy X", True),
    ("e088", "source:migration-run-103", "source:procedure-123",
     "EARLY_INSTANCE_OF", 0.5, 0.8, ("migration-run-103",),
     "The event-store migration is an early instance of the "
     "compatibility-first sequence", True),
    ("e089", "entity:schema-migration", "entity:event-store", "APPLIED_TO",
     0.4, 0.7, ("commit-112",), "Schema migration applied to the event "
     "store", True),
    # --- World D: constraints and baselines --------------------------------
    ("e090", "entity:importer", "source:benchmark-128", "BASELINE_IN", 0.5,
     0.85, ("benchmark-128",), "An early SQLite-only importer throughput "
     "baseline", True),
    ("e091", "entity:importer", "source:benchmark-126", "BASELINE_IN", 0.6,
     0.85, ("benchmark-126",), "The PostgreSQL importer throughput baseline",
     True),
    ("e092", "source:benchmark-126", "source:benchmark-128", "SUPERSEDES",
     0.6, 0.9, ("benchmark-126",), "The PostgreSQL baseline supersedes the "
     "SQLite-only one", True),
    ("e093", "entity:schema-migration", "source:policy-129", "CONSTRAINED_BY",
     0.7, 0.9, ("policy-129",), "Schema migrations must be reversible with a "
     "passing rollback test", True),
    ("e094", "entity:importer", "source:requirement-127", "CONSTRAINED_BY",
     0.65, 0.9, ("requirement-127",), "The importer must accept the v1 event "
     "representation until 2025-06-30", True),
    ("e095", "entity:importer", "source:incident-021", "FAILED_IN", 0.5, 0.85,
     ("incident-021",), "A concurrent importer run fails under write "
     "contention", True),
    ("e096", "entity:sqlite", "source:benchmark-128", "MEASURED_IN", 0.35,
     0.8, ("benchmark-128",), "SQLite-only importer throughput", True),
    ("e097", "entity:postgresql", "source:benchmark-126", "MEASURED_IN", 0.4,
     0.8, ("benchmark-126",), "PostgreSQL importer throughput", True),
    ("e098", "entity:postgresql", "source:runbook-006", "OPERATED_BY", 0.35,
     0.6, ("runbook-006",), "The runbook instructs operators on PostgreSQL",
     True),
    ("e099", "entity:backup-configuration", "entity:postgresql", "TARGETS",
     0.5, 0.8, ("commit-118",), "Backup configuration targets PostgreSQL "
     "after the move", True),
    ("e100", "entity:event-store", "entity:sqlite", "FORMER_BACKEND", 0.4,
     0.9, ("adr-003",), "SQLite was the former event-store backend", True),
    ("e101", "entity:event-store", "entity:postgresql", "CURRENT_BACKEND",
     0.75, 0.9, ("adr-007",), "PostgreSQL is the current event-store "
     "backend", True),
)


def build_graph() -> MemoryGraph:
    """Construct the ledger graph. Deterministic; no I/O, no model calls."""
    graph = MemoryGraph(
        version=GRAPH_VERSION,
        corpus_version=CORPUS_VERSION,
        notes=(
            "Derived from the project's canonical running examples. Source "
            "artifacts are authoritative; entity and claim nodes are derived "
            "interpretation and may be rebuilt."
        ),
    )
    for artifact_id, kind, date, description in ARTIFACTS:
        graph.add_node(
            MemoryNode(
                node_id=f"source:{artifact_id}",
                kind=SOURCE,
                label=artifact_id,
                description=f"{kind}: {description}",
                source_ids=(artifact_id,),
                terms=(kind, artifact_id),
                timestamp=date,
                derived=False,
            )
        )
    for entity_id, label, description, terms in ENTITIES:
        graph.add_node(
            MemoryNode(
                node_id=f"entity:{entity_id}",
                kind=ENTITY,
                label=label,
                description=description,
                source_ids=(),
                terms=terms,
            )
        )
    for claim_id, label, description, sources in CLAIMS:
        graph.add_node(
            MemoryNode(
                node_id=f"claim:{claim_id}",
                kind=CLAIM,
                label=f"{claim_id} {label}",
                description=description,
                source_ids=sources,
                terms=(claim_id,),
            )
        )
    for row in RELATIONS:
        (
            edge_id,
            source,
            target,
            relation,
            association,
            confidence,
            sources,
            description,
            bidirectional,
        ) = row
        graph.add_edge(
            MemoryEdge(
                edge_id=edge_id,
                source=source,
                target=target,
                relation=relation,
                description=description,
                association=association,
                evidence_confidence=confidence,
                source_ids=sources,
                bidirectional=bidirectional,
                derived=True,
            )
        )
    # Bind every claim to the source nodes that evidence it, so a path can
    # always end on raw evidence rather than on derived interpretation.
    for claim_id, _label, _description, sources in CLAIMS:
        for artifact_id in sources:
            source_node = f"source:{artifact_id}"
            edge_id = f"ev:{claim_id}:{artifact_id}"
            if any(edge.edge_id == edge_id for edge in graph.edges):
                continue
            existing = any(
                edge.source == f"claim:{claim_id}" and edge.target == source_node
                for edge in graph.edges
            )
            if existing:
                continue
            graph.add_edge(
                MemoryEdge(
                    edge_id=edge_id,
                    source=f"claim:{claim_id}",
                    target=source_node,
                    relation="EVIDENCED_BY",
                    description=f"{claim_id} is evidenced by {artifact_id}",
                    association=0.5,
                    evidence_confidence=0.9,
                    source_ids=(artifact_id,),
                    derived=False,
                )
            )
    return graph


# (case id, family, hop class, cue, expected sources, expected node path,
#  distractor sources, notes)
CUES: tuple[tuple, ...] = (
    # --- direct similarity should already succeed ------------------------
    ("c-direct-target", "decision", "direct",
     "What event store should new work target?",
     ("adr-007",), ("entity:event-store", "claim:evt-205", "source:adr-007"),
     ("adr-003",),
     "Control: a direct hit. Associative retrieval must not degrade it."),
    ("c-direct-redis", "decision", "direct",
     "What did the team decide about introducing Redis as a lookup cache?",
     ("adr-009", "session-044"),
     ("entity:redis", "claim:evt-206", "source:adr-009"),
     ("session-040",),
     "Control: the rejected proposal is the tempting nearby passage."),
    ("c-direct-production", "temporal", "direct",
     "What runs in production for the event store now?",
     ("deployment-101",),
     ("entity:event-store", "claim:fact-302", "source:deployment-101"),
     ("deployment-001",),
     "Control: production state, distinct from the decision."),
    # --- multi-hop: the target capability ---------------------------------
    ("c-hop-backup", "open-loop", "indirect",
     "What still had to move before the first release after the event-store "
     "migration?",
     ("session-051", "commit-118"),
     ("entity:event-store", "claim:evt-205", "source:commit-110",
      "source:commit-112", "claim:intent-401", "source:commit-118"),
     ("adr-007", "runbook-006"),
     "The completing artifact never names the release; it is reachable only "
     "through the migration chain."),
    ("c-hop-why", "provenance", "indirect",
     "Why was the event-store backend changed?",
     ("session-014", "session-019", "incident-021"),
     ("entity:event-store", "claim:evt-205", "claim:evt-203",
      "source:session-019"),
     ("session-033", "runbook-006"),
     "Evidence is two hops from the decision and does not name the "
     "decision."),
    ("c-hop-fixtures", "open-loop", "indirect",
     "Which test fixtures were left encoding assumptions from the old "
     "backend?",
     ("fixture-scan-109", "commit-120"),
     ("entity:event-store", "claim:evt-205", "entity:benchmark-fixtures",
      "source:fixture-scan-109"),
     ("benchmark-128",),
     "Weakly connected truth: the correct memories have low degree."),
    ("c-hop-facade", "decision", "indirect",
     "What prevents the compatibility facade from being deleted?",
     ("partner-note-004",),
     ("entity:corpus_import", "source:adr-013", "entity:partner-facade",
      "source:partner-note-004"),
     ("docs-note-012", "tests-compat-122"),
     "The constraint is one hop past the decision that created the facade."),
    ("c-hop-orphans", "provenance", "indirect",
     "What made the importer backfill permit orphaned rows?",
     ("incident-034",),
     ("entity:importer", "entity:strategy-x", "entity:foreign-key-checks",
      "source:incident-034"),
     ("incident-021",),
     "The cause is an entity-mediated chain, not a lexical match."),
    # --- context-conditioned branching ------------------------------------
    ("c-cond-silva-eventstore", "locate", "indirect",
     "What did a.silva propose about the event-store backend?",
     ("session-031",),
     ("entity:a.silva", "source:session-031"),
     ("adr-013", "issue-088", "incident-034"),
     "Same actor, event-store branch."),
    ("c-cond-silva-corpus", "locate", "indirect",
     "What did a.silva do about the legacy corpus_import callers?",
     ("issue-088", "adr-013"),
     ("entity:a.silva", "source:issue-088"),
     ("session-031", "incident-034"),
     "Same actor, corpus_import branch."),
    ("c-cond-silva-orphans", "locate", "indirect",
     "What did a.silva report about foreign-key checks and orphaned rows?",
     ("incident-034",),
     ("entity:a.silva", "source:incident-034"),
     ("session-031", "issue-088"),
     "Same actor, Strategy X branch."),
    ("c-cond-lindqvist-backend", "locate", "indirect",
     "What did j.lindqvist say about the SQLite backend preference?",
     ("session-033",),
     ("entity:j.lindqvist", "source:session-033"),
     ("partner-note-004", "procedure-123"),
     "Same actor, backend-preference branch."),
    ("c-cond-lindqvist-procedure", "locate", "indirect",
     "What schema-migration procedure did j.lindqvist record?",
     ("procedure-123",),
     ("entity:j.lindqvist", "source:procedure-123"),
     ("session-033", "partner-note-004"),
     "Same actor, procedure branch."),
    ("c-cond-okafor-callers", "locate", "indirect",
     "What corpus_import caller work was m.okafor assigned?",
     ("issue-089",),
     ("entity:m.okafor", "source:issue-089"),
     ("adr-007", "deployment-101"),
     "Same actor, web-caller branch; the event-store hub competes."),
    # --- adversarial -------------------------------------------------------
    ("c-adv-echo", "provenance", "adversarial",
     "Which episodes independently show a schema-first migration failing?",
     ("incident-026", "incident-105", "staging-run-104"),
     ("entity:schema-migration", "source:incident-026"),
     ("staging-log-018", "incident-106"),
     "The echo restates one episode and the same-symptom incident has a "
     "different cause; neither is independent support."),
    ("c-adv-tempting", "provenance", "adversarial",
     "What caused the nine-minute outage during a migration?",
     ("incident-026",),
     ("entity:schema-migration", "source:incident-026"),
     ("incident-106", "staging-log-018"),
     "A semantically tempting branch points at the wrong incident."),
    ("c-adv-stale", "temporal", "adversarial",
     "Is the recorded compatibility-first migration procedure still the one "
     "to follow?",
     ("procedure-123", "platform-note-125"),
     ("entity:schema-migration", "source:procedure-123",
      "source:platform-note-125"),
     ("run-124", "change-061"),
     "Stale association: the pathway was useful before the platform note."),
    ("c-adv-hub", "locate", "adversarial",
     "Which importer throughput baseline is current?",
     ("benchmark-126",),
     ("entity:importer", "source:benchmark-126"),
     ("adr-007", "deployment-101", "benchmark-128"),
     "Hub distraction: the event-store region dominates degree."),
    ("c-adv-superseded-task", "open-loop", "adversarial",
     "Is the SQLite performance-tuning work still worth doing?",
     ("issue-041", "adr-007"),
     ("entity:sqlite", "source:issue-041", "claim:evt-205"),
     ("session-033",),
     "The task is superseded; the preference passage is the distractor."),
    # --- abstention ---------------------------------------------------------
    ("c-abs-cache", "decision", "unanswerable",
     "What cache layer was adopted in front of the event store?",
     (), (), ("session-040", "adr-009"),
     "No cache was adopted; the Redis region is the temptation."),
)


def build_cases():
    """Materialise the cue set as instrument-facing cases."""
    from .evaluation.adapter import AssociativeCase

    cases = []
    for (
        case_id,
        family,
        hop_class,
        cue,
        expected_sources,
        expected_path,
        distractors,
        notes,
    ) in CUES:
        cases.append(
            AssociativeCase(
                case_id=case_id,
                cue=cue,
                family=family,
                expected_sources=tuple(expected_sources),
                expected_path=tuple(expected_path),
                distractor_sources=tuple(distractors),
                hop_class=hop_class,
                expected_status=(
                    "unanswerable" if hop_class == "unanswerable" else "answerable"
                ),
                notes=notes,
            )
        )
    return cases


def oracle_seed_nodes() -> dict[str, list[str]]:
    """Cue text -> the nodes the ledger says the case should start from.

    Used only by the oracle seeding condition, which separates a seeding
    failure from a propagation failure.
    """
    mapping: dict[str, list[str]] = {}
    for _case_id, _family, _hop, cue, _sources, path, _d, _n in CUES:
        mapping[cue] = list(path[:1]) if path else []
    return mapping


def cue_set_payload() -> dict:
    return {
        "cue_set_version": CUE_SET_VERSION,
        "graph_version": GRAPH_VERSION,
        "corpus_version": CORPUS_VERSION,
        "cases": [
            {
                "case_id": case_id,
                "family": family,
                "hop_class": hop_class,
                "cue": cue,
                "expected_sources": list(expected_sources),
                "expected_path": list(expected_path),
                "distractor_sources": list(distractors),
                "notes": notes,
            }
            for (
                case_id,
                family,
                hop_class,
                cue,
                expected_sources,
                expected_path,
                distractors,
                notes,
            ) in CUES
        ],
    }


def write_fixtures(root: Path) -> dict[str, Path]:
    """Write graph and cue JSON under ``root`` (``solution/fixtures/assoc``)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    graph_path = build_graph().save(root / "graph-v0.1.json")
    cue_path = root / "cues-v0.1.json"
    cue_path.write_text(
        json.dumps(cue_set_payload(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {"graph": graph_path, "cues": cue_path}
