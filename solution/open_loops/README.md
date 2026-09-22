# Open loops — companion implementation (Chapter 9)

Expected transitions and evidence of absence. Chapter 8's ordered
history is the substrate; this layer resolves whether known
expectations were satisfied, cancelled, or superseded — or remain open.

```text
oracle-labelled expectation (opening known; Ch10 earns extraction)
      +
Chapter 8 append-only event log (temporal_memory.EventLog)
      |
      v
status resolver (computed at query time and/or maintained)
      |
      v
StatusReport: status + opening/closing evidence + search footprint
```

An item is open because opening evidence exists and no valid closing
transition was observed — never because nothing was found. History gaps
force UNKNOWN. Deadlines are derived flags, not extra states.

## Commands (no services)

```bash
cd solution
python -m open_loops.cli demo
python -m open_loops.cli list --scope all
python -m open_loops.cli status intent-401
python -m open_loops.cli status intent-401 --valid-at 2024-07-20T00:00:00Z
python -m open_loops.cli history intent-401
python -m open_loops.cli explain intent-401
python -m open_loops.cli verify intent-401
python -m open_loops.cli reverify
python -m open_loops.cli health
python -m open_loops.cli benchmark --outdir ../experiments/benchmark/runs/ch9-test
```

## Benchmark

```bash
python ../solution/run_ch9.py
python -m pytest open_loops/tests/ -q
```

## Closure tiers (strongest first)

1. `state-transition` — the desired state is observed (diff/config/state);
2. `explicit` — authoritative complete/cancel/supersede marker;
3. `semantic` — commit text overlaps the opening statement (work artifacts only);
4. `textual` — a "done"-style claim (weakest).

Mentions never close mentions. Closing transitions must follow the
opening in event time. Expectations are derived state with recorded
provenance, even when oracle-labelled.
