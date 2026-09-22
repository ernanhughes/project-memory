# Chapters 9–14 — experiment slots

Non-published working notes. Each slot must be implemented under
`experiments/benchmark/` (generator, fixtures, queries, runs, analysis)
before the corresponding chapter's pending section can be converted
into a book result. Normative contract: `spec/benchmark-v0.1.md`
(Q5/Q6 families); open definitional questions live in
`spec/ch9-14-issues.md` and must be resolved per spec §9 before
fixtures freeze.

## E-09 — open loops and expected transitions (Ch 9)

Suite E9-A..E9-K plus deadline and second-domain experiments is
implemented in `solution/open_loops/` over a deterministic ledger
fixture reusing the frozen running-example IDs (`adr-007`,
`commit-112`, `commit-117`, `commit-118`, `session-040`,
`session-044`, `session-051`, `intent-401`, `issue-041`,
`release-024`). Openings are oracle-labelled/ledger-established;
commitment extraction stays with Chapter 10.

- E9-A mention baselines (M0/M1) — run.
- E9-B oracle opening + status over matched H1-H4 trajectories — run.
- E9-C cross-artifact semantic closure — run.
- E9-D side-effect state closure — run.
- E9-E maintenance vs derivation (+staleness probe, rebuild) — run.
- E9-F search footprint auditability — run.
- E9-G sequence gap → UNKNOWN — run.
- E9-H bitemporal actual vs believed status — run.
- E9-I long simulation + re-verification — run.
- E9-J snapshot corroboration (secondary) — run.
- E9-K perfect historian / bad colleague — run.
- Deadline flags, second-domain event trigger — run.

**Status: implemented and run (fixture-level).** Frozen run at
`experiments/benchmark/runs/ch9-20260920T000629Z-open-loops/`:
M0 precision/recall 0.8/0.8 with the Redis false positive;
canonical/oracle/cross-artifact/side-effect/bitemporal/gap/deadline
dimensions all 1.0 under maintained status; stale-open 3/3 cycles
without re-verification, 0 with; maintenance/derivation agree on
quality. Verdict Type A on fixture evidence with recorded demotion
clauses (oracle openings, no reader, synthetic). Zero model calls.

## E-10 — intention representation (Ch 10)

- Extends E-09 fixtures across the
  suggestion/intention/decision/consequence grid, plus
  retroactive-commitment cases (commitment established by later
  behaviour, not the originating utterance) and cross-artifact
  completions. Metrics add commitment correctness and transition
  accuracy. Important comparison: intention-aware tracking vs mention
  baseline on never-accepted and silently-completed classes.
- **Type-A.** Gains from commitment/completion evidence, residuals in
  retroactive cases → earns the intention record and quarantine rules
  (deadlines/dependencies recorded only when stated).
- **Type-B.** Pragmatic force unextractable at required reliability →
  restrict intentions to structured artifacts; session-derived
  obligations stay candidates.

## E-11 — explicit vs derived open loops (Ch 11)

- **Question.** Can the system infer consequences never written as
  tasks without inventing obligations?
- **Fixtures.** Explicit tasks, hidden consequences, false apparent
  consequences (contracted facade), intentionally preserved stale
  references (regression tests), deferred cleanups with scope
  conditions, partial migrations; trap-only fixtures for abstention
  scoring. Running example: corpus_import domain removal (adr-013,
  issue-088/089).
- **Conditions.** Difference-check with (current, expected,
  difference) triple evidence vs unconstrained obligation listing;
  ablations removing the current-state leg and expected-state leg.
- **Metrics.** Inferred-consequence precision/recall scored separately
  from explicit-task metrics; abstention on trap-only fixtures;
  evidence correctness on the reported triple.
- **Type-A.** Triple structure buys precision on traps/stale
  references with recall holding on hidden consequences → derived
  loops earned as a guarded capability with an explicit threshold
  operating point (precision/recall traced over the confidence
  threshold; operating point recorded as policy).
- **Type-B.** Precision collapses whenever recall rises above the
  explicit-task level → derived loops demoted to research notes
  (candidates with confidence, never findings).

## E-12 — behavioural measurement instrument (Ch 12) [REPLACES the
## obsolete situational-relevance design below; preserved in git history]

- **Question.** When the same model performs the same present task,
  does access to project memory change its behaviour, and is that
  change an improvement?
- **Fixtures.** Nine controlled BehaviourTasks (fix-store, ship-ch10,
  release-blockers, credit-rule, cite-rule, review-prose,
  review-arch, corpus-cleanup, irrelevant-control) with hidden
  behavioural ledgers and frozen grader contracts; five time-locked
  real-project transfer tasks. Implemented in
  `solution/behavior_eval/` (fixture v1, grader v1).
- **Conditions.** B0 no-memory / B1 full history / B2 strong RAG /
  B3 C5 frame-conditioned / B4 A6@768 assembled / BO auditable
  oracle / BA decisive-removed / BR decisive-restored / BW
  wrong-memory / BS scrambled substitution. Fixed reader
  (`llama3.1:8b@t0`), ministral-3:8b transfer check.
- **Metrics.** task_success plus constraint adherence,
  failure-avoidance, open-work continuation, current-state
  correctness, harmful-action rate (separate), goal adherence;
  influence/utility split; paired deltas; N/A is null, never zero.
- **Status: RUN.** `ch12-20260920T184500Z-behavior` (+ ministral
  transfer run, + real-transfer.json). Verdict Type A on fixture
  evidence with demotion clauses (see Ch 12). The old fixed-candidate
  similarity-vs-relevance experiment was refuted/absorbed by Ch 10
  and is not revived here.

## E-12 (superseded design, 2026-09-16 — similarity vs relevance)

- **Question.** ~~Does the task-useful ordering diverge from the
  resemblance ordering over the same candidates?~~ Chapter 10
  measured this directly (C0 identical bundles under two objectives,
  C4 overlap 0.031) and the design below never ran.
- **Fixtures (unbuilt).** ~~Present tasks paired with candidate sets
  engineered for divergence... Ledger records the ideal admission
  order...~~
- **Conditions (unbuilt).** ~~Similarity ordering vs state-informed
  reordering with the retrieved candidate set held fixed...~~
- **Metrics (unbuilt).** ~~Selection quality + spec Q6 downstream
  bridge metrics...~~
- **Type-A (unreached).** ~~Reordering improves task-critical recall...~~
- **Type-B (unreached).** ~~Similarity already places task-critical
  memories first...~~

## E-13 — retrieval-policy comparison (Ch 13)

- **Question.** Does explicit admission policy beat resemblance, and
  does resemblance-optimal admission ever behave worse?
- **Fixtures.** Same-store design: all systems receive identical
  events/beliefs/provenance/intentions/loops; only admission policy
  differs. Policy ladder A (similarity only) → B (+validity filter)
  → C (+unresolved-state boost) → D (task-conditioned ranking);
  per-signal ablations.
- **Metrics.** Downstream task performance (constraint adherence,
  failed-approach avoidance, open-work continuation) alongside
  conventional retrieval metrics, distraction/token/harmful-memory
  rates (spec Q6). The resemblance-vs-behaviour tension is a primary
  observable, not a side note.
- **Controls.** Highly similar obsolete memories; weakly similar
  causal memories; old authoritative constraints; conflicting and
  duplicated memories; high-cost relevant memories. Policy
  configuration (thresholds, boosts) frozen per run contract.
- **Type-A.** B/C/D improve behaviour while resemblance metrics stay
  flat or decline → policy earned as an explicit layer; metric
  tension reported as a finding.
- **Type-B.** Downstream tracks resemblance across policies → collapse
  Ch 12–13 into retrieval tuning; defer policy (and learned rankers).

## E-14 — context-assembly pressure test (Ch 14)

- **Question.** Does assembly buy anything over selection once load grows?
- **Fixtures.** Load-graded admitted sets: small/large relevant sets,
  duplicates, echoes, contradictions, stale background; selection
  frozen at a strong policy.
- **Conditions.** Raw vs ordered vs deduplicated vs validity-marked
  admission, traced as load grows at matched budgets.
- **Metrics.** Task performance (adherence, avoidance, continuation),
  token/distraction cost; failure classes scored distinctly (cost,
  duplication waste, contradiction, staleness, focus loss).
- **Type-A.** Assembled conditions hold performance where raw
  admission degrades, classes separating by condition → assembly
  earned as a layer independent of policy; motivates the
  compression/consolidation block.
- **Type-B.** Nothing beats raw admission at any load → bottleneck
  overstated at current budgets; defer assembly machinery.

## Cross-cutting before any result counts

- Ch 2 leakage controls extended per the Q5/Q6 lists above.
- Frozen run manifests per spec §6 (including policy configuration
  for E-13 and threshold operating points for E-11); per-question
  reporting per spec §7; benchmark versioning per spec §9.
- Real-corpus validation for each earned mechanism, adjudicated
  manually with disagreements preserved.
