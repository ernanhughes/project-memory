# Memory book — companion implementation

Ten layers, one dependency order. Each layer keeps the cheaper layers
available underneath it and never becomes the only route to history.

```text
memory_baseline      Chapter 3 — conventional RAG over raw history
graph_memory         Chapter 4 — persistent derived graph (GraphRAG 3.1.2)
associative_memory   Chapter 5 — cue-conditioned propagation over the graph
memory_nexus         Chapter 6 — routing/control across memory mechanisms
evidence_lineage     Chapter 7 — support groups, derivation lineage, retraction
temporal_memory      Chapter 8 — ordered trajectories, bitemporal state (ZeroMQ transport, append-only log)
open_loops           Chapter 9 — expected transitions, open-loop status, search footprints
context_frames       Chapter 10 — project/work frames, context bundles, selection traces
derived_loops        Chapter 11 — derived consequences with staged triple gate
behavior_eval        Chapter 12 — behavioural instrument: paired memory
                     interventions, deterministic simulator, ledger grading
```

Raw sources stay canonical; every derived layer is rebuildable and
versioned; fallback always runs downward to strong RAG and raw evidence.
ZeroMQ is transport, never the store: the temporal log is canonical and
projections rebuild from it.

## Tests

```text
python -m pytest solution/ -q
```

Default paths cover every package suite (`graph_memory`,
`associative_memory`, `memory_nexus`, `evidence_lineage`,
`temporal_memory`, `open_loops`, `context_frames`, `derived_loops`,
`behavior_eval`)
plus the shared `tests/` directory and the continuity guard
(`solution/tests/test_continuity.py`).
Unit tests need no services. Live integration (PostgreSQL, Ollama,
GraphRAG indexing, DRIFT queries) is exercised through the
`run_ch*.py` drivers, never through unit tests.

## Services per demo

- No external service: `associative_memory` demo and fixture suites,
  `evidence_lineage` suite, `context_frames` unit tests (lexical-only
  retrieval, labelled as such), continuity checks.
- PostgreSQL (via `docker compose up -d pg`): `memory_baseline`
  ingest/search/ask and the Ch3/Ch4 runners.
- Ollama (`bge-m3`, `llama3.1:8b`, `ministral-3:8b`): embeddings,
  readers, GraphRAG extraction.
- GraphRAG (`graphrag==3.1.2`, in `solution/.venv`): index builds and
  Basic/Local/Global/DRIFT queries.

## Canonical runners

```text
python solution/run_ch3.py    # Chapter 3 ladder and comparisons
python solution/run_ch4.py    # Chapter 4 matched-reader comparison
python solution/run_ch8.py    # Chapter 8 temporal suite
python solution/run_ch9.py    # Chapter 9 open-loop suite
python solution/run_ch10.py   # Chapter 10 context-frames ladder
python solution/run_ch11.py   # Chapter 11 derived-loops gate
python solution/run_ch12.py   # Chapter 12 behavioural interventions
python solution/run_ch14.py   # Chapter 14 assembly over frozen C5 input
```

Assembly demo (no services):

```text
cd solution
python -m context_frames.assembly_cli
```

## Capstone (integrated remembering system)

Composition only — no new memory mechanism. C4 = strong retrieval +
temporal/evidence resolution + explicit frames + staged trust gate + bounded
assembly + ContextTrace, evaluated by the behavioural instrument:

```text
python solution/run_capstone.py --mode replay   # deterministic, no services
python solution/run_capstone.py --mode live --model llama3.1:8b  # model-backed
```

Replay re-executes the integration over frozen validated contexts
(`ch12-20260920T204414Z-behavior` + token-control + real-transfer) and freezes
a new run under `experiments/benchmark/runs/capstone-*/`. See
`planning/capstone-contract.md` and `planning/capstone-implementation-report.md`.

Every run freezes its manifest (corpus/task versions and hashes,
models, budgets, prompts, code commit) under
`experiments/benchmark/runs/`.
