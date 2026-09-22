# context_frames — Chapter 10

Goal- and project-conditioned context construction. Retrieval finds what
resembles the query; this layer decides what the remembered past should
contribute to the work being done now, under a fixed context budget, and
records why.

```text
ProjectFrame          durable, versioned project policy (configuration)
      │
WorkSignal(s)         user message / event / tool result / failing test /
      │               scheduled job / agent task / project state
WorkFrame             what is being done now, citing the signals behind it
      │
Candidate retrieval   Chapter 3 hybrid search, plus frame-conditioned
      │               objective expansion and class pull
Eligibility           project scope, supersession, class absence
      │
Signals               query / goal / project / temporal / evidence /
      │               open-loop / relational / recency / redundancy
Coalescing            echo folding, disagreement preserved, temporal notes
      │
Budget admission      fixed token budget
      │
ContextBundle  ─────► the exact evidence the model sees
ContextTrace          why every candidate was admitted or rejected
```

No memory carries a stored `priority`. Importance is computed against a
frame and written to the trace, never onto the memory.

The trace records full decision evidence for **rejected** candidates as
well as admitted ones — retrieval source, raw score, eligibility
decisions, frame signals, the stage that disposed of it, budget state and
final disposition. A trace that only explains admissions can say what the
model saw but not why it never saw what it needed.

## Relationship to the other layers

| Layer | What it supplies here |
|---|---|
| Ch3 `memory_baseline` | the candidate generator, unchanged |
| Ch4/Ch5 graph, associative | adjacency between admitted evidence |
| Ch7 `evidence_lineage` | support versus echo versus refutation |
| Ch8 `temporal_memory` | supersession as of the frame time |
| Ch9 `open_loops` | unresolved work, weighted by the work type |

`memory_baseline.context.ContextTrace` is Chapter 3's admission trace and
is a different object from this package's `ContextTrace`, which records
the frames, the policy version and a decision for every candidate.

## Running it

```text
python -m context_frames.cli demo        # same query, two goals
python -m context_frames.cli ladder      # C0-C6 plus the oracle ceiling
python -m context_frames.cli build --task T1-architecture --condition C6
python -m context_frames.cli why --task T1-architecture --unit mb-method-earn
python -m context_frames.cli rejected --task T1-architecture
python -m context_frames.cli backtest    # policy revision under gates
python solution/run_ch10.py              # frozen E10 run
```

Unit tests need no services and run the retriever lexical-only, which is
weaker than any reported configuration and says so through
`HybridRetriever.describe()`. Reported runs use `bge-m3` embeddings and
the `llama3.1:8b` reader at temperature zero, matching Chapter 3.

## The ladder

| Condition | Context construction |
|---|---|
| `C0` | strong RAG, query only — the Chapter 3 baseline |
| `C1` | C0 plus a recency preference over recent work |
| `C2` | C0 restricted to the project scope |
| `C3` | C2 plus the ProjectFrame's default class policy |
| `C4` | C3 plus the WorkFrame: objective-expanded recall, work-type policy |
| `C5` | C4 plus the Chapter 7, 8 and 9 signals and candidate pulls |
| `C6` | C5 plus adjacency, coalescing and redundancy |
| `CO` | the ledger oracle: what the budget physically permits |

Reader, corpus, query and token budget are fixed across every rung.

## Policy revision

`backtest.py` proposes frame revisions, replays every task under each,
and promotes only when the primary metric improves with no gate breached.
A candidate frame is an immutable version; promotion is a recorded
decision. Nothing adapts online.
