# Temporal memory — companion implementation (Chapter 8)

Ordered transitions between remembered states. ZeroMQ is transport;
the append-only event log is memory.

```text
ZeroMQ transport (PUB -> XSUB/XPUB proxy -> SUB recorder)
      |
      v
Event Recorder (adds received_at, ingest_seq only)
      |
      v
append-only event log (JSONL, canonical, deterministic replay)
      |
      v
Temporal Engine (reducer + standpoint queries)
```

## One-command demo (no services)

```bash
cd solution
python -m temporal_memory.cli demo
python -m temporal_memory.cli permutations postgres-migration
python -m temporal_memory.cli trajectory event-store.backend
python -m temporal_memory.cli query --subject event-store.backend \
  --valid-at 2026-07-20T00:00:00Z --known-at 2026-08-10T00:00:00Z
python -m temporal_memory.cli health
python -m temporal_memory.cli replay --out /tmp/ch8-events.jsonl
```

## Live ZeroMQ demo

```bash
python -m temporal_memory.cli demo --live
python -m temporal_memory.cli benchmark --outdir ../experiments/benchmark/runs/ch8-test --live
```

The live path runs an in-process XSUB/XPUB proxy, three publishers
(benchmark, decisions, deployment), a readiness gate (recorder
subscribes before any publisher sends; no sleep-based correctness),
controlled send delays, capture with arrival metadata, then freezes
the log. All model comparisons replay the frozen log.

## Benchmark

```bash
python ../solution/run_ch8.py            # emulated-disorder frozen run
python ../solution/run_ch8.py --live     # live-transport frozen run
python -m pytest temporal_memory/tests/ -q
```

## Event log format

Each JSONL line: `{"envelope": {...}, "received_at": ..., "ingest_seq": N}`.
Envelope schema `temporal-event-v0.1`: event_id, source_id, source_seq,
event_type, subject, state_key, value, event_time, recorded_at,
effective_from/to, causal_parents, supersedes, corrects, evidence_refs,
payload. History is never rewritten; corrections append.

## Query standpoint

`state.bitemporal(subject, valid_at, known_at)`: given what was known
by `known_at`, what was valid at `valid_at`. Different standpoints give
different correct answers; that is bitemporal memory, not a bug.
