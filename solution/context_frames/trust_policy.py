"""Trust / authority gate: which memories may influence behaviour.

A staged, deterministic admission policy. Every candidate unit ends as
admit, deny or quarantine with a reason code from the control flow
taken. Quarantine excludes from context like deny, but counts
separately: quarantined items are suspicious, denied items are
settled.

The governing constraint: trust governs whether evidence may
influence behaviour; it never converts evidence into truth. No stage
asserts content truth. Corroboration counts independent lineages; it
never manufactures authority.

Cumulative ladder (each layer adds falsifiable behaviour):

* S1 provenance-only deny: revoked, revocation-tainted derivation,
  unresolvable provenance, or naive instruction screen (imperative
  content from a non-authoritative artifact class). No scope,
  authority, validity, restriction, or corroboration logic.
* S2 authority + scope: S1 plus project-scope isolation plus
  kind-authority (preferences never guide action; ungrounded
  derivations never count).
* S3 authority + scope + corroboration: S2 plus, on consequential
  tasks, action-directing content (decisions, instructions, derived
  claims) requires ledger-authoritative currency or independent
  corroboration. Informing content (evidence, proposals) is not held
  to the corroboration bar: evidence informs, decisions direct.
* FULL trust gate: S3 plus temporal validity, restriction scopes,
  conflict quarantine, and corroboration-aware instruction handling
  (refuted-by-authority denies, corroborated admits, neither
  quarantines) replacing the naive screen.

Instruction screening is textual and deterministic (fixed pattern
list); corroboration and refutation ride visible lineage refs
(derived_from / refuted_by), never hidden labels. Maliciousness is
never an input flag: the gate must earn poison blocking from content
and structure, or fail visibly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TRUST_POLICY_VERSION = "trust-policy-v1.1"

# Deterministic imperative patterns. Deliberately narrow: standing
# rules worded as requirements ("require a passing rollback test")
# must not trip it; only bypass/skip/ignore-class directives do.
INSTRUCTION_PATTERNS = (
    r"skip (\w+ ){0,3}(validation|verification|checks|testing|review)",
    r"ignore (\w+ ){0,3}(normal|the|all|any|migration checks)",
    r"bypass",
    r"disable (\w+ ){0,3}(validation|verification|checks|foreign-key)",
    r"never verify",
    r"do not (\w+ ){0,3}(verify|check|test|validate)",
    r"without (\w+ ){0,3}(validation|verification|review|approval)",
    r"regardless of (\w+ ){0,3}(existing|prior|current)",
    r"always skip",
)
_INSTRUCTION_RE = re.compile("|".join(INSTRUCTION_PATTERNS))

AUTHORITATIVE_ARTIFACTS = ("adr", "deployment")
AUTHORITATIVE_KINDS = ("decision", "production_state")
NON_GUIDING_KINDS = ("preference",)

VERDICTS = ("admit", "deny", "quarantine")


@dataclass(frozen=True)
class Unit:
    """One candidate memory with observable features only.

    ``claim`` is the normalized statement (visible derived metadata,
    Ch7-style extraction). ``derived_from`` / ``refuted_by`` are
    visible lineage refs. ``revoked`` / ``restricted_to`` are visible
    registry state. Nothing here says whether content is true.
    """

    unit_id: str
    kind: str
    project: str
    date: str
    text: str
    claim: str = ""
    artifact_kind: str = "session"
    valid_from: str = ""
    valid_until: str = ""
    derived_from: tuple[str, ...] = ()
    refuted_by: tuple[str, ...] = ()
    revoked: bool = False
    restricted_to: str = ""


@dataclass(frozen=True)
class TaskPacket:
    task_id: str
    query: str
    as_of: str
    project: str
    caller_scope: str = "agent"
    consequential: bool = True


@dataclass(frozen=True)
class Admission:
    unit_id: str
    verdict: str  # admit | deny | quarantine
    reason: str
    stage: str


def instruction_like(text: str) -> bool:
    return bool(_INSTRUCTION_RE.search(text.lower()))


def _roots(unit: Unit, by_id: dict[str, Unit]) -> frozenset:
    """Chain-end sources: units with no derived_from reachable above."""
    roots = set()
    stack = [unit.unit_id]
    visited: set[str] = set()
    while stack:
        uid = stack.pop()
        if uid in visited:
            continue
        visited.add(uid)
        u = by_id.get(uid)
        if u is None or not u.derived_from:
            roots.add(uid)
        else:
            stack.extend(u.derived_from)
    return frozenset(roots - {unit.unit_id} or {unit.unit_id})


def independent(u1: Unit, u2: Unit, by_id: dict[str, Unit]) -> bool:
    """Disjoint root lineages (same unit is never independent)."""
    if u1.unit_id == u2.unit_id:
        return False
    return not (_roots(u1, by_id) & _roots(u2, by_id))


def corroborators(unit: Unit, pool: list[Unit],
                  by_id: dict[str, Unit],
                  ignore: str | None = None) -> list[str]:
    """Other units, same claim, disjoint lineage, unrefuted.

    ``ignore`` names the counterpart of a refutes-relation under test:
    refutes involving only that pair are overlooked, so corroboration
    can be assessed while a dispute is examined. Everywhere else, any
    refutes mark disqualifies (conservative).
    """
    out = []
    if not unit.claim:
        return out
    for other in pool:
        if other.unit_id == unit.unit_id:
            continue
        if other.claim != unit.claim:
            continue
        if not independent(unit, other, by_id):
            continue
        other_ref = [r for r in other.refuted_by if r != ignore]
        unit_ref = [r for r in unit.refuted_by if r != ignore]
        if other_ref or unit_ref:
            continue
        out.append(other.unit_id)
    return out


def _revocation_tainted(unit: Unit, by_id: dict[str, Unit]) -> bool:
    """True when any record in the unit's transitive derivation
    closure is revoked. Unresolvable refs are skipped (provenance
    handles them elsewhere). Narrow T7 rule: derivation never
    launders revoked standing, at any policy level."""
    stack = list(unit.derived_from or ())
    seen: set[str] = set()
    while stack:
        uid = stack.pop()
        if uid in seen:
            continue
        seen.add(uid)
        src = by_id.get(uid)
        if src is None:
            continue
        if src.revoked:
            return True
        stack.extend(src.derived_from or ())
    return False


def _authoritative_current(u: Unit, as_of: str) -> bool:
    return (u.kind in AUTHORITATIVE_KINDS
            and (not u.valid_until or u.valid_until >= as_of))


@dataclass
class GateResult:
    admissions: dict[str, Admission] = field(default_factory=dict)

    def admitted_ids(self) -> list[str]:
        return sorted(uid for uid, a in self.admissions.items()
                      if a.verdict == "admit")


def _deny(uid: str, reason: str, stage: str) -> Admission:
    return Admission(uid, "deny", reason, stage)


def _admit(uid: str, reason: str, stage: str) -> Admission:
    return Admission(uid, "admit", reason, stage)


def _quar(uid: str, reason: str, stage: str) -> Admission:
    return Admission(uid, "quarantine", reason, stage)


def apply_policy(units: list[Unit], task: TaskPacket,
                 level: str) -> GateResult:
    """Run one policy level over all units. Deterministic; no model."""
    assert level in ("S1", "S2", "S3", "FULL")
    by_id = {u.unit_id: u for u in units}
    res = GateResult()
    for u in units:
        res.admissions[u.unit_id] = _decide(u, task, level, by_id, units)
    return res


def _decide(u: Unit, task: TaskPacket, level: str, by_id: dict,
            pool: list[Unit]) -> Admission:
    # Stage 1-3 (S1 core): revocation, provenance, naive instruction.
    if u.revoked:
        return _deny(u.unit_id, "deny.revoked_source", "revocation")
    if _revocation_tainted(u, by_id):
        # T7: derivation does not launder revocation. A unit whose
        # source chain contains a revoked record cannot retain
        # independent action-authority through that chain. This is
        # standing, not truth: content is not declared false.
        return _deny(u.unit_id, "deny.revoked_source",
                     "revocation-inheritance")
    if u.kind == "derived_restatement":
        if not u.derived_from or any(
                r not in by_id for r in u.derived_from):
            return _deny(u.unit_id, "deny.untrusted_source", "provenance")
    if (instruction_like(u.text)
            and u.artifact_kind not in AUTHORITATIVE_ARTIFACTS):
        if level == "S1":
            return _deny(u.unit_id, "deny.memory_instruction",
                         "instruction-naive")
    if level == "S1":
        return _admit(u.unit_id, "admit.relevant_context", "s1-pass")
    # S2+: scope isolation, then source class (unverifiable producers
    # denied here, so S1 alone admits them: measured difference).
    if u.project != task.project:
        return _deny(u.unit_id, "deny.cross_scope", "scope")
    if u.artifact_kind in ("unknown", "external"):
        return _deny(u.unit_id, "deny.untrusted_source", "source-class")
    # S2+: kind authority.
    if u.kind in NON_GUIDING_KINDS:
        return _deny(u.unit_id, "deny.untrusted_source", "authority")
    if u.kind == "derived_restatement" and not _grounded(u, by_id):
        return _deny(u.unit_id, "deny.untrusted_source",
                     "authority-ungrounded-echo")
    if level == "S2":
        return _admit(u.unit_id, "admit.relevant_context", "s2-pass")
    # FULL-only temporal and restriction checks precede corroboration so
    # superseded/restricted records fail with their own reason codes.
    if level == "FULL":
        if u.valid_until and u.valid_until < task.as_of:
            return _deny(u.unit_id, "deny.superseded_as_current",
                         "validity")
        if u.restricted_to and u.restricted_to != task.caller_scope:
            return _deny(u.unit_id, "deny.private_scope", "restriction")
        if instruction_like(u.text):
            return _instruction_admit(u, task, pool, by_id)
    # S3 (and FULL): corroboration requirement on consequential tasks
    # for action-directing content. Informing kinds (evidence,
    # proposals) are exempt: they inform action without directing it.
    if (task.consequential and u.kind not in ("evidence", "proposal")
            and not _established(u, task, pool, by_id)):
        return _deny(u.unit_id, "deny.uncorroborated", "corroboration")
    if level == "S3":
        return _pass(u, task, pool, by_id)
    # FULL: conflict quarantine, then pass.
    if _corroborated_conflict(u, pool, by_id):
        return _quar(u.unit_id, "quarantine.conflicting_evidence",
                     "conflict")
    return _pass(u, task, pool, by_id)


def _grounded(u: Unit, by_id: dict) -> bool:
    """Echo chains terminate at a non-derived record (Ch7 rule)."""
    seen: set[str] = set()
    stack = list(u.derived_from)
    while stack:
        uid = stack.pop()
        if uid in seen:
            continue
        seen.add(uid)
        src = by_id.get(uid)
        if src is None:
            return False
        if src.kind != "derived_restatement":
            return True
        stack.extend(src.derived_from)
    return False


def _established(u: Unit, task: TaskPacket, pool: list[Unit],
                 by_id: dict) -> bool:
    """Ledger-authoritative currency, grounded echo of a currently
    authoritative source (echoes inherit standing, never create it),
    or one independent corroborator (two disjoint lineages, since
    corroborators are independent by construction)."""
    if (u.kind in AUTHORITATIVE_KINDS
            and (not u.valid_until or u.valid_until >= task.as_of)):
        return True
    if u.kind == "derived_restatement" and _grounded(u, by_id):
        for root in _echo_roots(u, by_id):
            src = by_id.get(root)
            if src is not None and _authoritative_current(src,
                                                          task.as_of):
                return True
    return len(corroborators(u, pool, by_id)) >= 1


def _echo_roots(u: Unit, by_id: dict) -> set[str]:
    """Ultimate non-derived sources of an echo chain."""
    roots: set[str] = set()
    stack = list(u.derived_from)
    seen: set[str] = set()
    while stack:
        uid = stack.pop()
        if uid in seen:
            continue
        seen.add(uid)
        src = by_id.get(uid)
        if src is None or src.kind != "derived_restatement":
            roots.add(uid)
        else:
            stack.extend(src.derived_from)
    return roots


def _pass(u: Unit, task: TaskPacket, pool: list[Unit],
          by_id: dict) -> Admission:
    if u.kind in AUTHORITATIVE_KINDS:
        return _admit(u.unit_id, "admit.current_authoritative", "authority")
    if corroborators(u, pool, by_id):
        return _admit(u.unit_id, "admit.corroborated", "corroboration")
    return _admit(u.unit_id, "admit.relevant_context", "relevance")


def _corroborated_conflict(u: Unit, pool: list[Unit],
                           by_id: dict) -> bool:
    """Both sides of a refutes edge corroborated: quarantine, not pick.
    Each side's corroboration is assessed overlooking only the dispute
    under test."""
    for rid in u.refuted_by:
        other = by_id.get(rid)
        if other is None:
            continue
        if (corroborators(u, pool, by_id, ignore=rid)
                and corroborators(other, pool, by_id,
                                  ignore=u.unit_id)):
            return True
    for other in pool:
        if u.unit_id in other.refuted_by and corroborators(
                u, pool, by_id, ignore=other.unit_id) and corroborators(
                other, pool, by_id, ignore=u.unit_id):
            return True
    return False


def _instruction_admit(u: Unit, task: TaskPacket, pool: list[Unit],
                       by_id: dict) -> Admission:
    """Corroboration-aware instruction handling (FULL only)."""
    for rid in u.refuted_by:
        other = by_id.get(rid)
        if other is not None and _authoritative_current(other, task.as_of):
            return _deny(u.unit_id, "deny.memory_instruction",
                         "instruction-refuted")
    if corroborators(u, pool, by_id):
        return _admit(u.unit_id, "admit.corroborated",
                      "instruction-corroborated")
    return _quar(u.unit_id, "quarantine.suspected_poison",
                 "instruction-unverified")
