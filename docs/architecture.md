# Project Memory Architecture

## Design goal

Answer one question behaviorally: does retained project history
change what the same acting model does now, and is that change
better? Everything in this repository exists to make that question
answerable under controlled conditions — or it does not ship.

## Historical record vs memory vs authority

Three layers, three different jobs:

```text
HISTORY
What happened?
Raw artifacts: sessions, commits, ADRs, issues, deployments.

MEMORY
Which parts of that past are relevant to the present task?
Retrieval, temporal validity, scope, framing, assembly.

AUTHORITY
Which relevant memories have standing to influence action?
Trust admission: admit, deny, or quarantine with reason codes.

READER
What action follows from the supplied evidence?
```

A preference can answer *where did we discuss X* while being
insufficient to authorize *what should we do now*. Revoked
authority is not a false proposition. Quarantined memory is not
deleted history. Low standing is not irrelevance. The architecture
keeps these distinctions structural: trust governs influence, never
historical existence or truth.

## Task routing

Question semantics decide which pipeline stages may run
(`simulator/pipeline.py`, `route_for()`):

```text
recall / historical (Q1, Q-recall)
→ retrieval + temporal interpretation
→ trust authority must not erase legitimate historical visibility

state / explanatory (Q2–Q5)
→ retrieval + appropriate temporal interpretation

action / influence (action tasks, probes)
→ full policy: temporal, scope, frame, trust, S2 assembly

control / no-memory (echo controls)
→ no history
```

Unknown task families raise instead of defaulting. Routing is what
prevents the q-000018 failure mode (authority filtering applied to
a recall question) from recurring by construction.

## Retrieval baseline

Lexical word-overlap ranking (`simulator/actors.py`,
`rank_lexical_views()`), shared byte-identically by the
rule-actor baseline and the Muse C2 condition so the two retrieval
paths cannot drift apart. Top-5 for Muse conditions. The baseline
is deliberately credible: on ordinary tasks it scores 1.0, which
is what makes its failures (0.7273 with 3 harms on rule actors,
steered everywhere under adversarial memory) informative rather
than straw.

## Temporal validity

`simulator/temporal.py`: at a standpoint, records whose validity
interval ended are not current guidance. Excludes superseded
decisions and production states, preserves order, sees nothing
else — scope, poison, and revocation pass through untouched by
design. Measured: stale-only steering (0.0 + harm) removed with
zero behavioral cost on legitimate history (`sim-muse-c3-v1`).

## Scope

`simulator/scope.py`: views attributed to a foreign project do not
enter context for this task's project. Attribution rides explicit
view project tags (system state); the filter reads tags, never
text. Measured: metadata-only foreign scope steered Muse 6/6 with
3 harms; the filter removes the harm at zero behavioral cost
(`sim-muse-c4-v1`). Explicit textual scope declarations were
already refused by the reader unaided — the mechanism earns only
the metadata-invisible case.

## Frame establishment and frame safety

Frames are fixed kind-filters over views (`simulator/frames.py`):
naive hard framing admits only matching views (exclusion); safe
framing orders matching views first with no exclusion. Establishment
classes are fixed per probe (corroborated, weak, conflicting,
stale, unknown, known-bad) with the Chapter 13 policy mapping
applied unretuned. Measured (`sim-muse-c5-v1`): naive hard framing
degrades almost everywhere it excludes decisive evidence
(FW 0.09, FS/FB 0.0); safe policy recovers to 1.0 throughout. The
characteristic failure shape: missing decisive evidence yields
safe abstention, while present misleading evidence yields
confident wrong action.

## Trust and standing

The authoritative policy lives in the Memory repository
(`solution/context_frames/trust_policy.py`, currently
`trust-policy-v1.1`); this repository adapts ledger views to its
input shape and records verdicts (`simulator/trust_gate.py`). No
policy logic is duplicated here. Stages: revocation registry,
provenance, naive instruction screen (S1); plus scope isolation
and kind-authority (S2); plus corroboration on consequential tasks
(S3); plus temporal validity, restriction scopes, conflict
quarantine, and corroboration-aware instruction handling (FULL).
Reason codes come from control flow, e.g. `deny.cross_scope`,
`deny.revoked_source`, `deny.memory_instruction`,
`deny.superseded_as_current`, `deny.private_scope`,
`quarantine.suspected_poison`,
`quarantine.conflicting_evidence`, `admit.current_authoritative`,
`admit.corroborated`.

## Revocation inheritance

T7 rule, narrow: a derived unit whose transitive derivation
closure contains a revoked source cannot retain independent
action-authority (`deny.revoked_source`, stage
`revocation-inheritance`), at every policy level. Standing, not
truth: content is never declared false. This closed the one
independently reproduced defect in the trust layer (echo of a
present revoked source previously admitted).

## Final S2 assembly

The full assembler (grouping, echo collapse, redundancy removal,
explicit budgeting) did not earn itself: on the evaluated family
it ties decisive-evidence-plus-source-provenance behaviorally
while costing more context. The shipping rule is S2 — decisive
units plus source provenance — adopted by pre-registered
simplification verdict, not by preference for simplicity. A6
remains measured but not shipped.

## Reader boundary

Muse Spark via OpenCode (`muse-spark-1.3-contributor`, temperature
0, low reasoning effort, unique session per call) is the canonical
acting reader because the capstone must not depend on a small
model being incapable. Capability and memory are separate axes:
the reader compensates for some retrieval weakness but cannot
invent hidden project state (scope metadata, revocation state,
authority state, missing current decisions).

## Behavioral evaluator

Rule actors propose structured targets scored deterministically
against the hidden ledger (`simulator/scores.py`): exact
normalized match succeeds; superseded options are harmful
(`harm.superseded`); everything else fails without harm. Every
outcome carries reason codes (`ok.current`, `miss.*`). Muse rows
use the same scorer on parsed `TARGET:` actions; unparseable or
errored output abstains (`unknown`, 0.0), never guesses. Q-tasks
use deterministic id/yes-no/echo scoring (`simulator/qeval.py`).

## End-to-end trace

A worked action-task call under the integrated policy:

```text
present task (new service, topic, as_of cut)
↓
retrieval candidates (all task-cut views)
↓
temporal decision (drop valid_until <= as_of; reason per id)
↓
scope decision (drop foreign project tags; reason per id)
↓
frame decision (pass-through: no frame uncertainty asserted)
↓
trust decision (admit/deny/quarantine + reason code per unit)
↓
decisive evidence + provenance (S2 assembly + trace)
↓
Muse action (TARGET parse, unique session)
↓
deterministic outcome / score (ledger truth, harm codes)
```

Every inclusion and exclusion is attributable. The trace, not the
score, is the scientific product.

## Mechanisms measured but not shipped

A6 full assembly, generic redundancy reduction beyond echo
collapse, explicit token budgeting as capability, per-reader
policy tuning, learned ranking. Each was measured
against simpler alternatives and lost on behavior, cost, or both.
They remain in the codebase and frozen runs as evidence, not as
architecture.
