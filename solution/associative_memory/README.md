# associative_memory — Chapter 5

Associative retrieval over a persistent memory graph.

Chapter 3's baseline (`memory_baseline`) retrieves passages that resemble
the query. Chapter 4 (`graph_memory`) persists derived structure with
provenance back to source artifacts. This package asks what happens when
activation is allowed to move through that structure.

```text
cue
 ↓  seeding        lexical | embedding | hybrid | oracle
seed activation
 ↓  propagation    direct | pagerank | spreading | conditioned
activated subgraph
 ↓  decay, fan division, inhibition, threshold, budgets
selected memories + retrieval trace
 ↓
context
```

## Four quantities, kept apart

| quantity | meaning | where it lives |
|---|---|---|
| `relation` | what the edge asserts about the world | `MemoryEdge.relation` |
| `association` | retrieval priority, not truth | `MemoryEdge.association` |
| `evidence_confidence` | epistemic support for the proposition | `MemoryEdge.evidence_confidence` |
| `activation` | how strongly this cue lights the node up | `ActivationState`, per query |

Collapsing any two into one number is the design error the chapter is
about.

## Layout

```text
associative_memory/
    config.py            every parameter that defines a run
    pipeline.py          cue in, bounded selection and trace out
    fixtures.py          the deterministic ledger graph and cue set
    experiments.py       E5-A .. E5-H
    cli.py               fixtures | health | recall | compare | experiments | demo
    graph/adapter.py     MemoryGraph; adapter from a Chapter 4 snapshot
    seeding/             how a cue enters the graph
    propagation/         the four candidate mechanisms + shared selection
    activation/          state, decay, fan division, lateral inhibition
    pathways/            traces, versioned weights, Stage-B learning
    evaluation/adapter.py  bridge to the Chapter 2 instrument + path metrics
    health/checks.py     structural diagnostics
    tests/               105 tests, no services required
```

## Commands

Deterministic demonstration — no model server, no database, no network:

```bash
cd solution && python -m associative_memory.cli demo
```

Rebuild the committed fixture:

```bash
cd solution && python -m associative_memory.cli fixtures
```

Graph diagnostics:

```bash
cd solution && python -m associative_memory.cli health
```

One cue across every strategy:

```bash
cd solution && python -m associative_memory.cli compare "Why was the event-store backend changed?"
```

One cue with its full retrieval traces:

```bash
cd solution && python -m associative_memory.cli recall "What still had to move before the first release after the event-store migration?" --strategy spreading
```

The experiment suite, written to `experiments/benchmark/runs/<run-id>/`:

```bash
cd solution && python -m associative_memory.cli experiments --run-id ch5-local
```

Tests:

```bash
cd solution && python -m pytest associative_memory/tests -q
```

## Limitations

- The suite measures **retrieval**, not answers. No reader runs, so no
  claim is made about answer correctness against Chapter 3 or Chapter 4.
- The fixture graph is hand-built from the canonical running examples.
  Consuming a real Chapter 4 GraphRAG snapshot goes through
  `graph.adapter.from_graphrag_snapshot`, which is implemented and unit
  tested against a stub but has not been run against a real index.
- Embedding seeding defaults to the deterministic hashing embedder, which
  preserves no semantics. Runs that use it are a lower bound, and are
  labelled as such in the report.
- Stage B (adaptive pathways) is off by default and behind
  `LearningConfig.enabled`. Chapter 18 owns outcome adaptation; this
  package only makes the mechanism and its failure mode visible.
