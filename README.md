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
