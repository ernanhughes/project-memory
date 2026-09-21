# Capstone tickets (T1–T2 implemented; rest specified)

## T1 — Action simulator

IMPLEMENTED 2026-09-21 (`simulator/`): deterministic world state
from the hidden ledger, new-service task family (11 tasks;
rejection topics yield no task), rule actors (null, oracle,
lexical, superseded/preference probes), deterministic scorer with
reason codes, ledger overlays (remove/add, revalidated, frozen
fixtures never mutated). Remaining: further task families, more
intervention ops beyond remove/add.

## T2 — Baseline ladder

IMPLEMENTED 2026-09-21 with T1, frozen run
`experiments/benchmark/runs/sim-v0.1/`: null 0.0/0 harm, oracle
1.0/0, lexical 0.727/3 harms, superseded 0.0/3, preference 0.0/1.
Manifest with per-file checksums; verify clean. (Rule-actor
ladder; memory-condition ladder awaits trust port T7.)

## T3 — Open loops, assembly, outcomes, procedures

Add each only where repository state and book experiments require
it, following the already-measured book order (loops → assembly →
outcomes → procedures). Acceptance per layer: pre-registered
positive control plus ablation, frozen run committed.

## T4 — Causal mini-worlds

Hidden ledger encodes decision → action → outcome edges as
authoritative ground truth for controlled scenarios (SQLite
contention chain; migration → stale-fixtures chain). Acceptance:
intervention/counterfactual questions (what happened / why / what
worked / what failed / what to repeat / what to avoid / what if the
old approach returned) scored against ledger edges; no causality
inferred from mere sequence (guarded by test).

## T5 — CLI surface

`pm ingest/ask/open-loops/context/explain/trace/replay/record-outcome/
quarantine/revoke/audit/benchmark` exposing real architecture only;
no commands for appearance. Acceptance: every command maps to an
implemented module; replay/benchmark reproduce frozen runs.

## T6 — MCP surface

Small model-independent tools (`recall`, `current_truth`,
`explain`, `open_loops`, `assemble_context`, `record_outcome`,
plus `quarantine`, `request_restricted_memory`) usable by multiple
models. Acceptance: two different models complete one capstone
task through the surface with identical memory state.

## T7 — Port trust fixtures

Port the book trust fixtures (book runs `trust-dev-v1`,
`trust-eval-v1-*`) into generator fixtures under a new corpus
version once ledger-schema.md lands: RECONCILIATION items from
spec/running-examples.md, RESERVED_SUFFIXES extended, hygiene
confirmed, v0.1 untouched. Acceptance: frozen corpus builds with
all audits passing; trust experiment reproduces book verdicts.
