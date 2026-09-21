# Trust / admission policy

Status: **MEASURED.** The authoritative implementation remains in
the Memory repository (`solution/context_frames/trust_policy.py`,
currently `trust-policy-v1.1`); it is adapted here, never
duplicated (`simulator/trust_gate.py` maps ledger views to its
input shape and records verdicts). This document describes what
the policy is, as built.

Reference runs: `trust-dev-v1`, `trust-eval-v1-llama`,
`trust-eval-v1-muse` (book repo) and `sim-muse-c6-v1` (here).

## Rule

Trust governs whether evidence may influence behaviour; it never
converts evidence into truth. Admission ends admit, deny, or
quarantine with a reason code from the control flow. Quarantine
excludes from context like deny and counts separately.

## Stages (cumulative ladder S1/S2/S3/FULL)

1. Scope isolation: unit project vs task project → `deny.cross_scope`.
2. Source class: unverifiable producer → `deny.untrusted_source`.
3. Revocation registry: revoked → `deny.revoked_source`.
4. Provenance: derived without resolvable refs → `deny.untrusted_source`.
5. Kind authority: preferences never guide; ungrounded echoes never
   count → `deny.untrusted_source`.
6. Temporal validity: superseded as current guidance →
   `deny.superseded_as_current`.
7. Restriction scope: caller outside scope → `deny.private_scope`.
8. Instruction handling: imperative content refuted by authoritative
   current records → `deny.memory_instruction`; independently
   corroborated → admit; neither → `quarantine.suspected_poison`.
9. Conflict: both sides of a refutes edge corroborated →
   `quarantine.conflicting_evidence` for both, never pick a side.
10. Relevance ranking: content-word overlap, top-k (k=8), tie-break by
    unit id.

S1 runs stages 3 (revocation/provenance) plus a naive instruction
screen only. S2 adds 1, 2 (known classes), 5. S3 adds corroboration
for action-directing content on consequential tasks (evidence and
proposals inform without directing, and are exempt). FULL is all
stages with corroboration-aware instruction handling.

## Revocation inheritance (v1.1)

A derived unit whose transitive derivation closure contains a
revoked source cannot retain independent action-authority
(`deny.revoked_source`, stage `revocation-inheritance`), at every
policy level. Standing, not truth: content is never declared
false. This closed the one independently reproduced defect in the
policy (echo of a present revoked source previously admitted).

## Corroboration

Same normalized claim from disjoint root lineages, unrefuted.
Self-reinforcing restatements sharing one root never corroborate
each other. Echoes inherit the standing of their ultimate source;
they never create standing.

## Metrics

Attack success (designated attack units admitted), benign retention,
false-positive blocking, cross-project leakage, revoked influence,
quarantine rate, provenance coverage, token cost — plus behavioural
task success and harmful-action counts through the unchanged
behaviour grader. Simplification rule: adopt the simplest breach-free
policy with no worse task, harm, attack, and retention. Never
average readers.
