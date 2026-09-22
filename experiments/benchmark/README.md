# Benchmark experiments

This directory will hold the executable harness, corpus generator, frozen benchmark inputs, run manifests, and result summaries for the six-question Memory benchmark.

## Intended layout

```text
experiments/benchmark/
├── generator/          # controlled project-history generator
├── fixtures/           # generated or hand-authored frozen inputs
├── queries/            # versioned query sets
├── runs/               # run manifests and compact result summaries
├── analysis/           # scripts/notebooks used to compute tables and figures
└── README.md
```

Large raw artifacts should not be committed blindly. Prefer deterministic generation, checksums, compact result records, and pointers to externally stored artifacts when required.

The normative benchmark contract is `spec/benchmark-v0.1.md`.
