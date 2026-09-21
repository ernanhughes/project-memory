# Capstone benchmark contract

Status: **MEASURED.** This contract describes what was actually
built, frozen, and run. Historical proposals it supersedes are
noted where they differ.

## Task families

Action tasks (11-task frozen new-service family, plus OL/RV/CX
probes): propose an implementation target; scored by exact
normalized match with reason codes; superseded options harmful.

Question tasks (held-out expansion): Q1/Q2 id-listing against
frozen expected sets; Q3 support-chain id-listing; Q4 yes/no
verdicts; Q5 open-item id-listing at explicit cuts; Q-recall full
listing; Q-irr echo control. All scored deterministically
(set equality order-insensitive, boolean match, substring
containment). No LLM judges anywhere.

Q6 selection (deterministic, no reader): admitted-set vs
ledger-derived oracle-set precision/recall.

## Hidden ledger

Authoritative decisions, validity intervals, supersession and
support edges, provenance, task state, project scope. The
system-visible corpus is rendered from it; the system under test
never sees labels, edges, or expected answers. Leakage is
audited, not assumed.

## Visibility boundary

Three disjoint classes, enforced by construction and test:

* evaluator-side: ledger records, expected answers, oracle sets,
  probe designations, intervention overlays;
* reader-visible: rendered artifact text, display ids, dates,
  task text, standpoint;
* system-side memory metadata: validity state, project tags,
  derivation refs, revocation registry, reason codes, admission
  verdicts.

The second must never leak the first; the policy (not the
reader) consumes the third.

## as_of semantics

Every task carries an explicit standpoint. Artifacts dated after
it are excluded before any other processing. Corpus end
(2027-06-30) is the default only where a task states no cut.

## Evidence groups

Support chains (decision plus its `supported_by` artifacts),
echo groups (derivations sharing a root), and conflict pairs
(mutual refutes with independent corroboration each side) are
first-class test objects, not emergent observations.

## Positive-control sensitivity

A fixture (or family) that cannot separate known-good from
known-bad conditions cannot be used as evidence for the mechanism
being tested. Sensitivity is established per family before any
control layer is evaluated: the wrong-memory gate (11/11
SENSITIVE), the frame probes (all six sensitive), the trust
probes (poison/conflict sensitive; revocation invisible by
design; low-authority abstains either way). Insensitive fixtures
stay in the runs, labeled, excluded from verdict denominators.

## Behavior scoring

Rule actors and Muse rows share one deterministic scorer:
1.0 exact match, 0.0 otherwise; superseded options and facade
deletion harmful; unparseable or errored output abstains (0.0),
never guesses. Q-tasks use the qeval scorers above.

## Harm

Harmful actions are ledger-defined and counted separately from
task success everywhere. No shipped condition has harmed where a
measured unsafe baseline did not harm more; the two priced trust
costs (quarantine decisiveness, revocation utility, both on the
strong reader) are reported as costs, not hidden.

## N/A semantics

Skipped probes (topics lacking the required history) and empty
oracle sets produce null scores excluded from applicable
denominators, never silent zeros. Skip rows never enter means;
skip counts are reported per condition.

## Reader policy

Muse Spark via OpenCode is the canonical acting reader (strong
enough that failures implicate memory, not capability). Local
rule actors provide the deterministic floor and ceiling. Readers
are reported separately and never averaged. Identical prompts
sharing one live call are composed with `inherited_from` marks,
never re-billed as independent evidence.

## Run freezing

Every frozen run records: run id, code commit with clean tree
enforced (dirty trees refuse), corpus version and digest, hidden
ledger seed, condition set, model identity and decoding
parameters, session policy, per-row outputs, and per-file
checksums verifiable via `generator.manifest.verify_manifest`.
Any change to a frozen variable creates a new run.

## Manifest provenance

Beyond the v0.1 fields: `code_commit` + `dirty_state`,
`corpus_digest`, provider identity (`opencode-zen-go`,
model, reasoning effort, temperature, budgets, session
policy), sibling-repo SHA plus provider/policy file hashes,
and trust-policy version assertions. A checkout pair is either
exactly reproducible or visibly not.

## Question-family routing

Recall (Q1, Q-recall): retrieval + temporal; authority must not
erase history. Explanatory/state (Q2–Q5): retrieval + temporal.
Action/influence: full policy (temporal, scope, frame, trust,
S2). Control (echo): no memory. Unknown families raise.
Routing is load-bearing, pinned in `tests/test_routing.py`.

## Known insensitive/contaminated fixtures

`eq-q5-01` (oracle itself fails: instrument failure, never in
headlines); `eq-q4-02` (no-memory succeeds: contaminated, never
evidence for memory). Preserved, labeled, excluded from
applicable denominators.

## Canonical run policy

Runs are append-only historical evidence: no regeneration, no
normalization, no in-place correction, no deletion, no reruns to
improve documentation. Documentation adapts to runs, never the
reverse. `sim-muse-v1` stays historical (uncommitted harness);
`sim-muse-v2` is canonical where v1 is cited.

## Null-denominator rule

Undefined/not-applicable metrics are null and excluded from
applicable denominators, never silently zeroed. This rule
generalizes the skip-row treatment to every metric in this
contract.
