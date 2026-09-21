# Ledger schema extension (specification)

Status: **SPECIFIED ONLY.** v0.1 (`generator/schema.py`) is
implemented and frozen. The fields below are specified for the trust
work and are not yet in the schema. Do not add them to v0.1 records
or fixtures; implement under a new corpus version when the trust
fixtures are ported.

## New optional record fields

```text
project: string, default "main"
  Scope label. Cross-scope records carry their project visibly.

trust: never a ledger flag
  Maliciousness/suspicion is detected from content and lineage, or
  missed visibly. No trust label is stored, by design.

revoked: boolean, default false
  Source revocation as visible registry state. Revoked records are
  stored and rendered; admission denies them.

restricted_to: string, default ""
  Scope label or empty (unrestricted). Stored; admissible only for
  callers in scope.

source_class: derived from artifact_kind
  session/commit/adr/issue/runbook/deployment/external/unknown.
  "unknown" and "external" producers are unverifiable: deny.
```

## New record kind

```text
instruction (artifact: session or commit)
  Historical text reading as an instruction. Renders as an ordinary
  session/commit (plausible enough to enter retrieval); carries no
  trust marking in content. Admission handles it via the
  corroboration-aware instruction rule (trust-policy.md stage 8).
```

## New scenario tags

`poisoned_instruction`, `malicious_derived`, `cross_project`,
`revoked_source`, `restricted_record`, `self_reinforcement`.

## Suffix discipline

Trust display IDs use the 501–510 block proposed in
spec/running-examples.md. On implementation, extend
`generator/worlds.py` RESERVED_SUFFIXES with the block; parametric
allocation (1000+) is unaffected. Render new kinds through
`generator/render.py` with at least three surface realisations each
(audit template-diversity applies); trust metadata must never leak
into bodies (extend FORBIDDEN_SUBSTRINGS with trust vocabulary and
confirm the frozen v0.1 corpus still passes hygiene).
