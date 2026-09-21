# Project Memory Reproducibility

## Fully deterministic

These run with no credentials, no network, and no model. Same
inputs always produce byte-identical outputs (pinned by tests):

```text
corpus generation      python -m generator.build --repo-root .
audits                 five leakage audits gate every freeze
hidden-ledger evaluation (expected answers derived mechanically)
rule-actor runs        python -m simulator.run
admission policies     S1/S2/S3/FULL over any unit pool
filters                temporal, scope, frame, assembly
manifest verification  generator.manifest.verify_manifest
tests                  python -m pytest -q  (currently 128)
```

Frozen corpora and deterministic runs reproduce exactly, including
`experiments/benchmark/fixtures/v0.1` and
`experiments/benchmark/runs/sim-v0.1`.

## Model-mediated

Muse runs need live provider access plus the sibling Memory
checkout. Everything else about them is pinned:

```text
provider: opencode-zen-go (opencode.ai Responses API)
model: muse-spark-1.3-contributor (resolved at runtime, recorded)
reasoning: low
temperature: 0
max output tokens: 2048 (4096 on empty-output retry)
session isolation: unique id per run/task/condition(/repeat)
```

Credentials resolve from the environment, in order:

```text
MEMORY_OPENCODE_API_KEY
OPENCODE_ZEN_API_KEY
WRITER_OPENCODE_API_KEY   (convenience fallback only)
```

Endpoint: `https://opencode.ai/zen/go`. No other configuration
exists; do not invent variable names.

## Sibling Memory dependency

Two imports reach outside this repository, both pinned rather
than duplicated (a single authoritative implementation is
preferable to a fork):

```text
providers.opencode   (model calls; file hash in run manifests)
context_frames.trust_policy (admission policy; version asserted
                             at import: trust-policy-v1.1)
```

Expected layout:

```text
<parent>/
  memory/          ernanhughes/memory at the SHA recorded in
                   provenance.provider_source_commit
  project-memory/  this repository
```

Run manifests record both SHAs plus the provider file hash, so a
checkout pair is either exactly reproducible or visibly not. The
freeze harness refuses to run with either working tree dirty.

## What reproduces exactly vs approximately

Exactly: every deterministic artifact, every admission decision,
every rendered context string, every manifest checksum.

Approximately: model generations. Temperature-0 calls have
reproduced exactly across runs so far (44/44 rows, 11/11 rows,
11/11 rows on three separate occasions), but the provider is
remote and the model is versioned by the vendor. Treat frozen
model outputs as historical evidence of what the model did, and
re-run rather than assume stability across months.

## Quick start (no credentials needed)

```bash
python -m pytest -q
python -m generator.build --seed 20240823 --worlds 12 \
    --out /tmp/pm-check --repo-root .
python -m simulator.run --repo-root .
```

Live Muse runs are separate commands, clearly marked, and never
required for deterministic reproduction:

```bash
python -m simulator.muse_ladder --run-id <id> \
    --conditions C0 C1 C2 CO \
    --out experiments/benchmark/runs/<id>
```
