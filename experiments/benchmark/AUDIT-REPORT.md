# H1 audit report — v0.1 frozen corpus (E-03 / E-04 support)

Seed: **20240823**. Parametric worlds: **12**. Corpus: **61 artifacts**
(49 record-backed, 12 context), **31 queries** (14 Q1, 14 Q2-decision,
3 Q2-production), **17 E-04 oracle cases**. Manifest:
`experiments/benchmark/fixtures/v0.1/manifest.json` (67 files, sha256
each). No benchmark result is claimed here — this report covers
construction integrity only.

## Audit outcomes at freeze

| Audit | Result | Detail |
|---|---|---|
| query-lexical-overlap | PASS | worst shared query/record word-run: 3 (< 5) |
| timestamp-neutrality | PASS | presence by kind 0.90–1.00 (spread ≤ 0.15) |
| template-diversity | PASS | every record kind uses ≥ 3 realisations |
| trivial-classifier | PASS | worst stump excess over majority: 0.06 (≤ 0.10) |
| evaluator-separation | PASS | corpus dir clean |

## Design decisions the audits forced

- **Ingestion order is a seeded shuffle, not chronological.** Chronological
  order correlates with scenario position (proposals before decisions)
  and was measurably predictive of authority. A crawler's order is
  arbitrary; we choose random-by-seed.
- **Timestamp absence is stratified by record kind (~12%).** Sessions are
  sometimes undated per the ledger, but a flat rate left small kinds
  (preference, evidence) systematically undated by chance. Stratified
  stripping makes absence independent of kind by construction.
- **Realisation choice is round-robin with seeded offset**, so
  template-diversity coverage is deterministic, not luck.
- **The classifier stump tries quartile splits only.** Searching every
  midpoint overfits N≈50 rows and flags noise; a usable shortcut must
  show at a quartile split.
- **Context artifacts** (12 World A artifacts backing no record) are
  covered by the separation and hygiene sweeps but excluded from
  record-label audits, which require labels to test.

## Known limitations (for H2 and beyond)

- Q1 expected answers are artifact-level; span offsets are deferred.
- Production-state records carry empty `supported_by`: they are grounded
  in their backing deployment artifact, not in other records.
- `gen-000001`-shaped internal IDs share numeric value 1 with
  `deployment-001`; namespaces are separate (internal vs display) and
  the suffix-uniqueness rule covers display IDs only. Flagged, not blocking.
- Q2-production exists for 3 topics (World A + 2 parametric T4 worlds).
- No retriever, memory system, or model call was implemented or run.
  Nothing in this report is a benchmark result.
