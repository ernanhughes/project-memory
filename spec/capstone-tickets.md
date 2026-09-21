# Capstone tickets (specified, unimplemented)

Each ticket below is executable work with acceptance criteria. None
is started. Implement in order; keep every phase green before the
next begins.

## T1 — Action simulator

Deterministic simulated project environment for action tasks
(capstone task families in spec/running-examples.md). The system
proposes an action changing simulated project state; the simulator
scores deterministically (no LLM judge where deterministic scoring
is possible). Acceptance: replay same task under multiple
conditions with identical transitions; intervention tests
(remove/restore/wrong/poisoned/revoked/cross-scope/outcome-changed)
attribute failure classes (retrieval/selection/temporal/
provenance/authority/assembly/reader/learning).

## T2 — Baseline ladder

No-memory / full-history / strong-RAG / structured / complete /
complete+trust-gate / oracle conditions over the simulator.
Acceptance: frozen run with manifests recording every PART XXIII
field; no successive condition assumed better — measured.

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
