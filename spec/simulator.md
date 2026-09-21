# Simulator: current architecture description

Status: **IMPLEMENTED** through the C7 measurement program
(`simulator/`, 128 tests). This document describes what each piece
is, replacing the earlier T1/T2 progress note.

## WorldState

Hidden-ledger truth at an explicit `as_of` cut: current decision
target per topic, superseded options (choosing one is harmful),
production state. Unparseable decisions yield no task rather than
a guessed one; rejection topics yield no task.

## Tasks

Eleven frozen new-service tasks (`simulator/tasks.py`; ids and
cuts pinned by test — any fixture edit retires the family).
Held-out expansion tasks (Q1–Q6, recall, overload, revocation,
conflict, irrelevant probes) live in `simulator/expansion.py`
with ledger-derived expected answers.

## Reader-visible views

Artifact views (`display_id`, `kind`, `date`, `title`, `body`,
plus a `project` tag defaulting to the main scope) are the only
thing test actors and the reader ever see. Ledger records,
validity intervals, edges, and expected answers never cross this
boundary; probes take hidden state explicitly and are documented
as evaluator-side.

## Actors

Null (silent), oracle (evaluator-side ceiling), lexical (unsafe
top artifact decides), superseded and preference (intervention
probes). Muse acts through the same artifact views via the
`muse_ladder` harness with unique sessions per call.

## Muse harness

`simulator/muse_ladder.py`: frozen condition ladders (C0/C1/C2/CO,
W-probes, F-probes, T-probes, A-ladder, E-conditions), exact-prompt
disk-cache semantics per run, skip rows that never enter means,
and a dirty-tree refusal for canonical freezes. C3–C7 refuse with
`NotImplementedError` where unbuilt — except all are now built;
C8+ still refuse.

## Wrong-memory probes

Constructed adversarial contexts over frozen tasks (stale-only,
misleading order, revoked, cross-scope explicit and metadata-only,
poison, oracle sets, frame-uncertainty pairs, trust probes).
Ledger-adjacent, never merged into the corpus; each carries the
skip rule for topics lacking the required history.

## C3 temporal

Validity filtering at standpoint; blind to scope, poison, and
revocation by construction (tested).

## C4 scope

Project-tag filtering; blind to staleness, poison, revocation
(tested). Metadata-only scope is the case that earns it.

## C5 frames

Fixed kind-filters with corroborated/weak/conflicting/stale/
unknown/known-bad establishment and the Chapter 13 policy mapping
applied unretuned; soft ordering without exclusion; query fallback
provably C2-identical.

## C6 trust

Adaptation over the imported Chapter 17 policy (no policy code
here); S-rows inherit by exact-string identity, asserted per
case. Revocation-inheritance defect pinned and fixed upstream
(trust-policy-v1.1).

## C7 assembly experiments

Deterministic selection/grouping/budgeting with per-unit trace
reasons. Verdict: S2 (decisive + provenance) matches FULL
behaviorally at a fraction of tokens — A6 not shipped.

## Final S2 selection

Decisive evidence plus source provenance. The shipping assembly
rule by pre-registered simplification verdict.

## Routing

`route_for()` in `simulator/pipeline.py`: recall tasks keep
history visible (no trust exclusion); explanatory tasks add
temporal interpretation; action tasks run the full policy;
controls receive no memory. Unknown families raise.

## Scoring

Exact normalized target match (1.0) else 0.0; superseded options
harmful; unparseable or errored output abstains (0.0), never
guesses. Q-tasks: id-set equality (order-insensitive), yes/no
match, echo containment. Every outcome carries reason codes.

## Harm

Harmful actions are ledger-defined (acting on superseded
operational state, deleting the contracted facade) and counted
separately from task success everywhere. No condition has harmed
where the policy gate stands, except the priced trust costs on
the strong reader (quarantine decisiveness, revocation utility).

## Frozen runs

`experiments/benchmark/runs/`: sim-v0.1, sim-muse-v1
(historical), sim-muse-v2 (canonical baseline),
sim-muse-wrong-v1, sim-muse-c3/c4/c5/c6/c7-v1, sim-muse-exp-v1.
Each carries results, manifest with code commit and per-file
checksums, and (for Muse runs) provider identity and usage.
Manifests verify clean via `generator.manifest.verify_manifest`.

## Evaluator-side vs reader-visible vs system metadata

Evaluator-side: hidden ledger, expected answers, oracle sets,
probe designations (revoked ids, refutes edges), intervention
probes. Reader-visible: rendered artifact text plus display ids,
dates, task text, standpoint. System-side memory metadata:
validity intervals, project tags, derivation refs, revocation
registry, reason codes. The second must never leak the first;
the third is what the policy (not the reader) consumes.
