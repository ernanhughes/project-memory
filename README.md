# Project Memory

Project Memory is the runnable companion and capstone for the book [*Memory*](https://github.com/ernanhughes/memory).

Its governing question is behavioural:

> Does the same AI perform the same present task better when relevant project history is available?

The project begins with a controlled, deterministic benchmark for the first four questions in the book:

1. Where did we discuss X?
2. What did we decide about X?
3. Why did we decide it?
4. Is it still true?

The first implementation milestone is deliberately narrow: build the controlled project-history generator and run E-03 and E-04. Later mechanisms such as intentions, consolidation, forgetting, outcome adaptation, and procedures are excluded until earlier experiments demonstrate that they are needed.

## Evaluation layers

- **Controlled corpus:** rendered project artifacts generated from a hidden authoritative ledger.
- **Real-project corpus:** a smaller manually adjudicated history used separately for ecological validation.
- **Conditions:** no memory, credible retrieval baselines, and candidate structured mechanisms only after the relevant failure is measured.
- **Evidence:** frozen run manifests, per-case outputs, exact source traces, and per-question metrics.

No benchmark result is claimed until its complete run artifact is committed.

## Controlled-corpus generator (H1: E-03 / E-04)

Ground truth: `spec/running-examples.md` on main. Contract: the Memory
repo's `spec/benchmark-v0.1.md`. The generator implements Q1/Q2 scope
only — World A as a canonical fixture plus N parametric worlds (default
12) built from the same five scenario templates. No Worlds B–D, no
intentions, no procedures yet.

```bash
python -m pytest -q                                  # 59 tests, incl. plant-a-leak
python -m generator.build --repo-root .              # seed 20240823, frozen to
                                                     # experiments/benchmark/fixtures/v0.1
```

Layout: `corpus/artifacts/gen-NNNNNN.md` + `corpus/queries.jsonl`
(system-visible; no answers) alongside evaluator-side `eval/`
(`ledger.jsonl`, `expected.jsonl`, E-04 `oracle*.jsonl`,
`build_meta.jsonl`). The build refuses to freeze unless all five
leakage audits pass; see `experiments/benchmark/AUDIT-REPORT.md`.

## Model-mediated ladder (Muse)

`simulator/muse_ladder.py` runs the same 11 new-service tasks
through Muse Spark with four frozen conditions (C0 no memory, C1
full history, C2 lexical top-5, CO oracle evidence); C3–C7 refuse
with `NotImplementedError` until their supplying systems exist.
Model calls live only in this harness and its frozen runs — the
deterministic T1/T2 core stays model-free.

```bash
python -m simulator.muse_ladder --run-id sim-muse-v2 \
    --out experiments/benchmark/runs/sim-muse-v2
```

## Status

Implemented:

- controlled generator
- deterministic T1 action simulator
- rule-actor T2 baseline
- Muse-first model-mediated baseline C0/C1/C2/CO

Measured:

- sim-v0.1
- sim-muse-v2
- sim-muse-wrong-v1 (adversarial positive controls; 11/11 SENSITIVE)

Not implemented:

- C3–C7
- integrated Q1–Q6 capstone
- trust port
- real-corpus validation
