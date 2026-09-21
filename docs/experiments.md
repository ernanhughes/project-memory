# Project Memory Experiments

## Experimental method

```text
define
measure
build
fail
diagnose
add only the mechanism earned by failure
rerun
simplify
```

Every mechanism below earned its place by repairing a measured
failure, survived a simpler alternative, or was rejected in
favor of one. Frozen runs are append-only evidence under
`experiments/benchmark/runs/`; documentation adapts to them,
never the reverse.

## Controlled corpus

The hidden authoritative ledger renders model-visible artifacts
(sessions, commits, ADRs, issues, deployments). The system under
test never sees ledger labels: validity intervals, supersession
edges, support structure, or expected answers. Leakage is
audited, not assumed: the corpus freezes only if all five audits
pass (`experiments/benchmark/AUDIT-REPORT.md`).

Fixture versions: `fixtures/v0.1` (Q1/Q2 scope, frozen). Later
experiments reuse the same frozen corpus; no fixture was ever
edited after freezing.

## Deterministic T1/T2

Rule actors (`null`, `oracle`, `lexical`, `superseded`,
`preference`) propose implementation targets scored
deterministically against ledger truth. Results
(`sim-v0.1`, 11 tasks × 5 conditions):

```text
condition    success   harmful
null           0.000       0
oracle         1.000       0
lexical        0.727       3
superseded     0.000       3
preference     0.000       1
```

Unsafe lexical retrieval is useful but harmful — the baseline the
rest of the program must beat on safety, not just success.

## Muse baseline

Same 11 tasks through Muse Spark (`sim-muse-v2`, canonical; v1
kept as historical evidence of an uncommitted harness):

```text
condition    success   harmful
C0             0.000       0
C1             1.000       0
C2             1.000       0
CO             1.000       0
```

The strong reader abstains with no memory and solves ordinary
retrieved-history tasks. Capability is established so that later
failures implicate memory, not reader weakness.

## Wrong-memory positive controls

Before evaluating any control layer, sensitivity had to be
established: does bad memory actually steer this reader?
(`sim-muse-wrong-v1`, 62 calls). It does, selectively:

```text
condition               success   harmful   n
W0 no memory              0.000       0    11
WC current decision       1.000       0    11
WS superseded-only        0.000       3     3
WM misleading order       1.000       0     3
WR revoked (invisible)    0.000       0     1
WX cross-scope            0.000       0    11
WP poison                 0.000       3    11
WO decision + support     0.727       0    11
```

Stale-only and poison steer destructively; cross-scope steers
silently everywhere; misleading order does not fool Muse (it
reads past recency to the current decision); revocation is
invisible in content. Skipped cells mark inapplicable probes
(topics lacking the required history), never missing data.

## C3

Stale-only WS contexts (0.0 + harm) vs temporal-filtered history:
11/11 correct, 0 harm (`sim-muse-c3-v1`). The filter provably
removes exactly the superseded set and provably ignores scope,
poison, and revocation (tested, not claimed).

## C4

Metadata-only foreign scope steered Muse 6/6 with 3 harms while
explicit textual scope was already refused unaided: scope exists
as system metadata the reader never receives, so the filter must
live in the architecture, not the prompt. C4 removes it at zero
behavioral cost (`sim-muse-c4-v1`). Reader-visible warnings and
system-owned metadata are different things.

## C5

Naive hard framing degrades almost everywhere it excludes
decisive evidence (FW 0.09, FS/FB 0.0, FC/FU 0.64); the safe
policy (soft ordering without exclusion, query fallback)
recovers to 1.0 on all 66 policy rows (`sim-muse-c5-v1`, 132
calls). Characteristic shape: missing decisive evidence yields
safe abstention; present misleading evidence yields confident
wrong action. Frame safety controls tail risk from exclusion.

## C6

Same-frame/same-scope probes with trust admission
(`sim-muse-c6-v1`, 71 live calls): the control holds (TC 0.73),
revocation stays invisible without system state (TR enforced with
no behavioral delta), low-authority preferences abstain either way,
poison beside authority is adjudicated correctly unaided
(TP 0.73 both arms), derived-of-withdrawn costs utility
(TD 1.0 → 0.0), and quarantine costs decisiveness (TX 0.27 →
0.0). The sister trust experiment in the Memory repository
measured the admission ledger directly: attack success 0.0 with
benign retention 1.0 on both readers, with quarantine and
revocation utility prices on the strong reader. The
revocation-inheritance gap (echo of a present revoked source
admitted) was reproduced independently here and fixed narrowly in
trust-policy-v1.1.

## C7

Full assembly ladder vs simplifications (`sim-muse-c7-v1`):
A0–A6/AO saturate at 1.0 while S1 fails split decisions (0.73)
and S2 (decisive + provenance) matches FULL behavior at a
fraction of the tokens on all 11 tasks. Verdict: ADOPT_SIMPLER.
The shipping rule is decisive evidence plus source provenance;
grouping, echo collapse, redundancy reduction, and budgeting are
measured but not shipped.

## Held-out expansion

New question families and probes over the frozen corpus plus
constructed adversarial content (`sim-muse-exp-v1`, 116 calls):

```text
condition    success   harmful
E0             0.000       0      (11 action tasks)
E1             1.000       0
E2             1.000       0
EA             1.000       0
EO             1.000       0
QE0            0.143       0      (14 Q-tasks)
QE1            0.357       0
QE2            0.571       0
```

RAG ties the full policy on ordinary action tasks (those tasks
do not behaviorally require the architecture; the adversarial
runs separately establish what happens when harmful evidence
surfaces). Structured policy helps where evidence selection is
the bottleneck (4 E2-only Q wins) and hurts once (a preference
excluded from a recall answer). Conflict probes show authority
handling earning behaviorally (mixed decision+preference harms;
E2 correct). Revocation probes confirm invisibility again.
Q6 selection: precision 0.04–0.08 at recall 0.8–1.0 — admission
is broad by design; selection remains assembly's job.

## Final experimental verdict

Bounded findings, no universal score:

* Temporal validity removes stale harm at zero behavioral cost.
* Scope filtering removes metadata-invisible foreign influence.
* Frame safety prevents exclusion-driven failure; fallback recovers.
* Trust admission suppresses attack to zero with retention held,
  at measured utility prices on quarantined and revoked content.
* Minimum sufficient assembly is decisive evidence plus
  provenance; larger assemblies tie behaviorally at higher cost.
* Strong RAG ties the full policy on ordinary tasks and loses
  where selection, authority, or standing decide.
* Recall and influence need different routing; authority must
  not erase history.

Exact run directories:

```text
experiments/benchmark/runs/sim-v0.1
experiments/benchmark/runs/sim-muse-v1        (historical)
experiments/benchmark/runs/sim-muse-v2        (canonical baseline)
experiments/benchmark/runs/sim-muse-wrong-v1
experiments/benchmark/runs/sim-muse-c3-v1
experiments/benchmark/runs/sim-muse-c4-v1
experiments/benchmark/runs/sim-muse-c5-v1
experiments/benchmark/runs/sim-muse-c6-v1
experiments/benchmark/runs/sim-muse-c7-v1
experiments/benchmark/runs/sim-muse-exp-v1
```

## What the experiments rejected

* **Full history is always bad**: false — full history scores 1.0 on ordinary tasks (`sim-muse-v2` C1); it fails only under adversarial or overload conditions.
* **Stronger models remove the need for project memory**: false — C0 abstains on all 11 tasks; the reader cannot invent project state.
* **More correct evidence is always better**: false — decision-plus-support underperforms the bare decision on some topics (WO 0.73 vs WC 1.0).
* **Every memory question should use the same authority gate**: false — recall needs historical visibility that action tasks must deny (q-000018 mechanism).
* **The most sophisticated assembler must be best**: false — S2 matches A6 behaviorally at a fraction of tokens (`sim-muse-c7-v1`).
* **Retrieval ranking errors automatically become behavioral errors**: false — misleading order reads at 1.0; only missing system state (scope, revocation, authority) reliably steers.
* **Trust is free**: false — quarantine and revocation carry measured utility prices on the strong reader.
* **Every proposed mechanism deserves to ship**: false — A6, generic redundancy reduction, explicit budgeting, and per-reader tuning were measured and declined.
