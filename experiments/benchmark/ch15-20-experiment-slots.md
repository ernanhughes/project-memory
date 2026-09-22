# Chapters 15–20 — experiment slots

> **SUPERSEDED CHAPTER MAP — 2026-09-20.** These notes preserve the former Chapters 15–20 experiment design as historical planning material. The published ending is now Chapter 15 *What Should Memory Keep?*, Chapter 16 *Learning From Experience*, and Chapter 17 *The Remembering System*. Do not interpret E-15…E-20 numbering below as the current chapter structure. See `planning/final-chapters-consolidation.md`. No old slot is silently promoted into a new Book Result.


Non-published working notes. Each slot must be implemented under
`experiments/benchmark/` (generator, fixtures, queries, runs, analysis)
before the corresponding chapter's pending section can be converted
into a book result. Normative contract: `spec/benchmark-v0.1.md`;
open definitional questions live in `spec/ch15-20-issues.md` and must
be resolved per spec §9 before fixtures freeze.

## E-15 — consolidation (Ch 15)

- **Question.** Does replacing repeated episodes with a supported
  pattern improve downstream behaviour without harmful
  generalization?
- **Hypothesis.** Episode-plus-claims match or trail raw episodes on
  recall-style queries but pull ahead on tasks needing synthesis;
  unconstrained consolidation underperforms on exceptions, echoes,
  expired patterns, cause mismatches.
- **Fixtures.** Stable repeated patterns; single-source repetition
  (echo traps via derivation edges); patterns with exceptions;
  time-bounded patterns; patterns that later expire; superficially
  similar episodes with different causes; post-consolidation
  exception arrivals (maintenance test).
- **Conditions.** Raw episodic retrieval vs episodes + consolidated
  claims; ablation stripping support sets and scope (pattern vs
  shorter-context effect).
- **Metrics.** Task success on pattern-relevant tasks; exception
  preservation; provenance retention (claim unfolds to episodes);
  temporal correctness on expired patterns; false-generalization
  rate on echo/cause-mismatch fixtures.
- **Controls.** Independent vs single-source repetition; changing
  environments; misleading correlations; temporal validity bounds.
- **Type-A.** Task gains with exceptions/provenance/expiry
  preserved → consolidation earned as guarded inference.
- **Type-B.** Episodes equal or generalization unpreventable →
  narrow to human-approved rules or reject automatic consolidation.

## E-16 — compression (Ch 16)

- **Question.** At what representation level, per question family,
  does behaviour break — and does structure preservation explain
  fidelity better than length?
- **Fixtures.** Same histories rendered at five levels (full
  artifacts, events, summaries, consolidated claims, aggressive
  packing); compression defect traps per class (exception,
  supersession, provenance, entity-merge, dropped loop, removed
  failure, certainty inflation).
- **Conditions.** Levels A–E; structural-vs-plain ablation at
  matched lengths (validity marks, status flags, support references
  retained vs plain prose).
- **Metrics.** Correctness per question family (the break profile);
  provenance/temporal/open-loop retention; context size; downstream
  behavioural effect. Token cost only if measured.
- **Controls.** Negation, role reversal, timestamp, exception,
  unresolved-task, and provenance-dependency details that small
  changes flip.
- **Type-A.** Clear per-family break profile with structured
  variants holding fidelity below plain lengths → layered
  compression with storage/context separation earned.
- **Type-B.** Nothing beats raw artifacts behaviourally, or plain
  matches structured → premature optimization; keep raw-plus-events.

## E-17 — forgetting (Ch 17)

- **Question.** Can availability management suppress stale
  competition without catastrophic removal?
- **Fixtures.** Old-but-crucial constraints (safety trap);
  recent-but-useless chatter; superseded beliefs; duplicates; old
  preservable failures; abandonable ideas; retrospective-only facts.
- **Conditions.** None / age-based / supersession-aware /
  usage-based / task-conditioned, at matched budgets and selection.
  Suppression inspectable per task (what was available, not just
  admitted).
- **Metrics.** Per-family correctness plus downstream behaviour;
  forgetting-correctness (retain crucial-old, suppress stale,
  archival accessibility); catastrophic-removal rate as gating
  metric — minimax scoring, means do not excuse removals.
- **Controls.** Old crucial information; recent noise; superseded
  facts needed retrospectively; failures worth preserving.
- **Type-A.** Stale suppression with zero catastrophic removals →
  forgetting earned as availability management; confidence/utility
  separation kept.
- **Type-B.** No policy beats none-baseline safely → restrict to
  supersession-driven archival; defer the rest.

## E-18 — outcome adaptation (Ch 18)

- **Question.** Does outcome-aware updating converge on causally
  useful memories, or amplify noise into lock-in?
- **Fixtures.** Tasks with ledger-known causal usefulness: memory A
  necessary, B irrelevant, C misleading, D conditional on X;
  stochastic outcomes; early-luck sequences; correlated distractors;
  late contradictory evidence; shifting environments.
- **Conditions.** Static ranking vs naive usage reinforcement vs
  outcome-aware updating with attribution ladder; validity gating
  on/off (precedence of state over outcome).
- **Metrics.** Selection quality and task success traced per round;
  lock-in rate (early-noise persistence) as primary negative
  metric; conditioning correctness for D-on-X.
- **Controls.** Lucky success, unlucky failure, irrelevant
  retrieved memories, causal-vs-correlated memories, changing
  task distributions.
- **Type-A.** Convergence on A, suppression of C, conditioning of
  D, robust to luck → adaptive updating earned with attribution
  ladder and validity gating.
- **Type-B.** Noise amplification, lock-in, or no benefit over
  static → narrow to human-confirmed updates or omit automatic
  adaptation.

## E-19 — procedural transfer (Ch 19)

- **Question.** Does explicit procedure retrieval beat episodic
  memory on task success without replay harm?
- **Fixtures.** Repeated task families with transfer structure:
  correct reusable procedures; obsolete procedures; hidden
  prerequisites; similar-wording tasks needing different methods.
  Running procedure: compatibility-first migration with checks.
- **Conditions.** No memory / episodic only / explicit procedure
  retrieval / adapted procedure retrieval.
- **Metrics.** Actual task success (migration correct, rollback
  passing, preconditions checked); blind-replay harm rate per
  class (obsolete, hidden-prerequisite, similar-but-different).
- **Controls.** Correct, obsolete, and precondition-sensitive
  procedures; superficially similar tasks with different methods.
- **Type-A.** Procedures beat episodes without replay harm, scope
  and versioning explaining the gap → procedural memory earned.
- **Type-B.** Episodes match, or harm swamps gains → restrict to
  human-authored/versioned procedures; auto-extraction to
  candidates.

## E-20 — behavioural capstone (Ch 20)

- **Question.** Does the structured memory system behave better
  than naive retrieval and no memory on realistic project tasks?
- **Fixtures.** Six task families (continue work, respect
  architecture, avoid failures, use procedure, recover rationale,
  detect constraint) with ledger-derived graders frozen pre-run;
  memory-should-matter and memory-should-not-matter matched pairs
  (Redis counterfactual pattern); real-project adjudicated subset.
- **Conditions.** No memory / naive retrieval / structured system;
  ablations (minus temporal, task, provenance, procedural,
  adaptation) only where prior experiments justify them.
  Versioned layer survival: exclude any mechanism its experiment
  rejected.
- **Metrics.** Behavioural throughout (correctness, completion,
  compliance, avoidance, constraint use, provenance, supersession
  handling, procedure reuse, unnecessary-change and
  hallucinated-memory rates, context/execution cost). Retrieval
  metrics diagnostic only. Rubrics frozen before runs.
- **Type-A (strong positive).** Material behavioural gain →
  thesis supported as stated.
- **Type-B variants (pre-registered).** Mixed (scope the claims
  per family); weak (naive captures most benefit — collapse to
  the minimal surviving architecture); negative (complexity
  without gain — the boundary mapped is the contribution).

## Cross-cutting before any result counts

- Controls per chapter lists above; Ch 2 leakage discipline
  extended to transfer tasks and grader contracts.
- Frozen run manifests per spec §6 (plus policy config, operating
  points, layer-survival versions); per-question reporting per
  spec §7; benchmark versioning per spec §9.
- Real-corpus validation for each earned mechanism and the
  capstone, disagreements preserved.
