# Action simulator

Status 2026-09-21: **T1 core and T2 rule-actor ladder IMPLEMENTED**
(`simulator/`, frozen run `experiments/benchmark/runs/sim-v0.1/`).
What remains specified-only: further task families, more
intervention ops, memory-condition ladder (awaits trust port T7).

## Design (as built)

World state answers from the hidden ledger at an explicit cut what
a correct proposal must target and which options are superseded
(choosing one is harmful: acting on superseded operational state).
Unparseable decisions yield no task rather than a guessed one;
rejection topics yield no task (no positive target exists).

Actors: null (silent), oracle (evaluator-side ceiling),
lexical (unsafe top artifact decides), superseded and preference
(evaluator-side intervention probes). Test actors see artifact
views only; probes take the hidden world explicitly and are
documented as such. Scoring is exact normalized match plus a
superseded-harm rule, every outcome carrying reason codes.

Overlays copy the ledger, apply remove/add surgery, and revalidate;
frozen fixtures are never mutated and overlay runs never freeze.

## Baseline reads (frozen)

null 0.0/0 harm; oracle 1.0/0; lexical 0.727/3 harms; superseded
0.0/3; preference 0.0/1. Unsafe retrieval is useful but harmful —
the capstone's first measured shape, mirroring the book's.
