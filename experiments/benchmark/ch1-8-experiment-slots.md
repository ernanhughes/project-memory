# Chapters 1–8 — experiment slots

Non-published working notes. Each slot must be implemented under
`experiments/benchmark/` (generator, fixtures, queries, runs, analysis)
before the corresponding chapter's pending section can be converted
into a book result. Normative contract: `spec/benchmark-v0.1.md`.

## E-03 — naive baseline profile (Ch 3)

- Frozen controlled corpus covering the spec's initial scenario list;
  frozen Q1–Q4 query set phrased independently of ledger vocabulary.
- Baselines: no-memory, lexical, embedding top-k at several budgets,
  embedding + rerank. Fixed context budgets across comparisons.
- Deliverable: per-question metrics + per-case outputs/evidence +
  token/latency/cost. Predicted profile (hypothesis only): strong Q1,
  steep drop on Q2–Q4 on matched cases.

**Status: implemented with development runs only.** Ladder, chunking,
reader, and context-sweep comparisons exist under
`experiments/benchmark/runs/ch3-20260919-*/` but carry known fixture
and scorer defects documented in the chapter (evt-204 identifier
collision, un-timestamped "today" questions, source-recall stage
inconsistency across conditions, unanswerable-cache adjudication).
No comparative book result is claimed; the `best` condition is reused
as the Chapter 4 rival.

## E-04 — persistent understanding vs strong RAG (Ch 4)

Retired: the former E-04 (retrieval-conditioned decision gap with an
oracle-retrieval condition earning an event schema) belongs to the old
Chapter 4. The stronger baseline overturned its *therefore*; the
proposal/preference/decision example moved to Chapter 4 as a reuse
investigation. The retirement and its reason are recorded here so the
intent is not silently dropped.

Replacement suite (persistent-understanding / GraphRAG comparison):

- E4-A strong Chapter 3 RAG vs Graph Basic at matched total context,
  same reader, same corpus and task set.
- E4-B Graph Local on entity/relationship-centred tasks.
- E4-C small global-synthesis family for community-report strengths.
- E4-D cross-query consistency over related question families.
- E4-E derived-state provenance completeness (source mapping per object).
- E4-F derived-state error observation (false/split entities, stale or
  missing summaries, and their downstream use).
- E4-G cost profile (index build, query latency, context tokens,
  storage; model-call accounting where the package exposes it).
- E4-H rebuild/version stability under frozen configuration.

**Status: developmental run frozen, not publication-grade.**
`experiments/benchmark/runs/ch4-20260919T205622Z/` holds best (14
tasks), graph-basic (14), graph-local (14), graph-global (8; both
global-family and both relational-family tasks missing). Adjudicated
decision exactness is 8–9/9 across full-coverage conditions with the
largest gap one case in nine; mechanical gaps trace to scorer
normalisation (missing alias list on the why-question, word-order
sensitivity on the Redis question) and a budget-composition confound
(graph conditions surrender a third of raw context to the derived
block). An `adjudication.json` addendum records the rescue rule and
per-cell verdicts. Verdict Type C with Type B core (developmental).

Outstanding before any of this becomes a benchmark result:

- Repaired scorer normalisation (alias lists, citation-format
  handling) and matched-composition rerun at equal raw budgets.
- E4-C synthesis family and E4-D consistency measurement.
- DRIFT cells (one diagnostic attempt timed out at 90 s; full matrix
  unmeasured — do not run blindly, see Ch 4 DRIFT section).
- Pre-registered verdict upgrade on the corrected run.

## E-05 — associative retrieval over the memory graph (Ch 5)

Retired: the former E-05 (event extraction gain vs cost) belongs to the
rebuilt Chapter 4's extraction work and moves there with it.

Suite E5-A..E5-H is implemented in
`solution/associative_memory/experiments.py`. A first frozen run over the
deterministic ledger fixture is committed at
`experiments/benchmark/runs/ch5-20260919-e5/e5-suite.json` (20 cues,
73-node graph, matched context budget of 8 memories).

**Status of that run: retrieval-level only.** No reader, no generated
answers, synthetic graph. It settles which memories propagation admits
and at what cost; it does not settle answer correctness, and no Chapter 3
versus Chapter 4 versus Chapter 5 comparison is claimed from it.

- E5-A direct versus associative retrieval — done (fixture). Includes the
  no-propagation floor, four propagation strategies, a degree-preserving
  edge-shuffle control, oracle seeding, and a seeding-method comparison.
- E5-B context-conditioned branching — done (fixture).
- E5-C multi-hop versus direct-case control — done (fixture).
- E5-D precision cost, per-constraint ablation — done (fixture).
- E5-E hub resistance on the adversarial subset — done (fixture).
- E5-F false-edge resilience with per-case effect — done (fixture).
- E5-G static versus outcome-gated adaptive pathways — done (fixture),
  behind the Stage-B flag.
- E5-H reinforcement pathology, frequency-only versus outcome-gated —
  done (fixture).

Outstanding before any of this becomes a benchmark result:

- Reader in the loop: the same admitted selections through the Chapter 3
  reader at matched context budgets, scored by the full instrument.
- Chapter 3 baseline and Chapter 4 static-graph conditions run on the
  same cue set, plus an oracle-path condition separating traversal
  failure from reasoning failure.
- A real Chapter 4 snapshot through `graph.adapter.from_graphrag_snapshot`
  (implemented and unit-tested against a stub; never run against an index).
- Real-corpus associative depth: the distribution of hops between the best
  available seed and the required evidence. Every result in the fixture
  run is conditional on that distribution, and it has not been measured.

## E-06 — Memory Nexus control matrix (Ch 6)

Retired: the former E-06 (substrate profile across
relation-sensitive pairs with similarity substrate as the independent
variable) belongs to the retired "Similarity Is Not Memory" chapter.
Its durable ideas migrated per the Chapter 6 migration record
(resemblance/state and accepted/rejected distinctions to Ch 3/4,
historical/current to Ch 8, representation-relative boundaries and
materiality thresholds kept as standards).

Replacement suite (routing/control): task-by-capability matrix over
the registered capabilities (`NONE`, `RAG`, `GRAPH_BASIC`,
`GRAPH_LOCAL`, `GRAPH_GLOBAL`, `GRAPH_DRIFT`, `ASSOCIATIVE`,
`RAW_EVIDENCE`) with fixed, random, rules, classifier, oracle, and
sequential policies.

**Status: partial.** `experiments/benchmark/runs/ch6-20260919-nexus/e6-suite.json`
holds 8 of 20 routing tasks (46 cells, 7 capabilities, one shared
reader, matched context budgets); DRIFT unmeasured and 12 tasks
pending live runs. See also `experiments/benchmark/runs/ch6-matrix/`.

## E-07 — provenance chains (Ch 7)

- Generator support-graph fixtures: multi-source decisions, qualifying
  evidence, echo documents, non-supporting distractors.
- Question 3 scorer: answer correctness, evidence coverage, provenance
  precision, support-chain validity, conditioned on Q1–Q2 correctness.
- Baselines: source-pointer citation vs chain retrieval; ablation with
  derivation edges removed.

**Status: implemented and run (fixture-level).** Suite E7-A..E7-J is
implemented in `solution/evidence_lineage/experiments.py` over a
deterministic ledger fixture reusing the frozen running-example IDs.
First frozen run committed at
`experiments/benchmark/runs/ch7-20260919-e7/e7-suite.json` (9 claims,
12 spans, 26 nodes, 20 edges, zero model calls). Verdict Type A on
fixture evidence; LLM-backed extraction/verification and real-corpus
validation remain open obligations recorded in the E-07 slot.

## E-08 — temporal trajectories (Ch 8)

Suite E8-A..E8-J plus a second-domain permutation is implemented in
`solution/temporal_memory/` over a deterministic ledger fixture reusing
the frozen running-example IDs (`adr-007`, `session-014`, `session-033`,
`session-040`, `session-044`, `incident-021`, `release-024`).

- E8-A bag vs ordered history — run.
- E8-B order-sensitive permutation (benchmark/decision swap) — run.
- E8-C order-invariant permutation (independent swap) — run.
- E8-D arrival-order disorder, live ZeroMQ capture + frozen replay — run.
- E8-E bitemporal late knowledge — run.
- E8-F future-effective decision — run.
- E8-G correction vs revision — run.
- E8-H partial order / concurrency — run.
- E8-I missing sequence / gap — run.
- E8-J computed vs materialized (+ rebuild equivalence, cost scaling) — run.
- Second-domain permutation (feature-flag incident) — run.

**Status: implemented and run (fixture-level).** Frozen runs at
`experiments/benchmark/runs/ch8-20260919T234349Z-temporal/` (emulated
disorder) and `experiments/benchmark/runs/ch8-20260919T234350Z-temporal/`
(live ZeroMQ transport): current-state accuracy 1.0 across all five
conditions (T0/T1/T1b/T2/T3); historical-state accuracy 0.0 for
T0/T1/T1b vs 1.0 for T2/T3; temporal-role, invariance, late-arrival,
future-effective, correction, partial-order, gap, rebuild, and
supersession dimensions all 1.0 under T3. Verdict Type A on fixture
evidence with recorded Type B/C/E demotion clauses. Zero model calls.
LLM-backed rendering and real-corpus validation remain open.

## Cross-cutting before any result counts

- Leakage controls from Ch 2 (answer, timestamp, template, lexical,
  query-duplication, evaluator privilege, pattern memorization).
- Frozen run manifests per spec §6; per-question reporting per spec §7;
  benchmark versioning per spec §9.
