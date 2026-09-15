"""Ledger schema for the v0.1 controlled corpus (H1: E-03 / E-04 only).

Ground truth lives in the Memory repo's ``spec/running-examples.md`` and the
Memory repo's ``spec/benchmark-v0.1.md`` contract. This module only defines
the *shape* of hidden records and validates them. It contains no benchmark
results and no model calls.

Record kinds in v0.1 scope (Q1/Q2 only):

- decision            authoritative project decision
- proposal            option introduced but not settled
- preference          personal stance; explicitly NOT a decision (E-04 distractor)
- evidence            observation / benchmark / incident supporting a decision
- production_state    fact about what currently runs (vs what was decided)
- derived_restatement echo of a decision; derived evidence, not independent support
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KINDS = (
    "decision",
    "proposal",
    "preference",
    "evidence",
    "production_state",
    "derived_restatement",
)

ARTIFACT_KINDS = (
    "session",
    "commit",
    "adr",
    "issue",
    "runbook",
    "deployment",
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DISPLAY_ID_RE = re.compile(r"^[a-z]+-\d+$")


class LedgerError(ValueError):
    """Raised when a hidden record or ledger violates the schema."""


@dataclass(frozen=True)
class Record:
    """One hidden ledger record.

    ``key`` is the ledger-internal stable key (e.g. ``evt-205``).
    ``display_id`` is the book artifact label rendered into content
    (e.g. ``adr-007``). Dates are ISO calendar dates; ``None`` for
    ``valid_until`` means current at corpus end.
    """

    key: str
    kind: str
    topic: str
    content: str
    actors: tuple[str, ...] = ()
    date: str = ""
    valid_from: str | None = None
    valid_until: str | None = None
    supersedes: tuple[str, ...] = ()
    supported_by: tuple[str, ...] = ()
    derived_from: tuple[str, ...] = ()
    display_id: str = ""
    artifact_kind: str = ""
    # Render directive (not ground truth): how the decision record reaches
    # artifacts. "crisp" = one ADR; "buried" = decision stated in a session;
    # "split" = decision content across two session artifacts, the second
    # named by second_display_id. Non-decision records always use "crisp".
    render_style: str = "crisp"
    second_display_id: str = ""
    # Scenario template that produced the record (one of the five H1
    # templates). Used for audit stratification and evaluator metadata.
    scenario: str = ""

    def validate(self, known_keys: set[str]) -> None:
        if self.kind not in KINDS:
            raise LedgerError(f"{self.key}: unknown kind {self.kind!r}")
        if not self.topic or not self.content:
            raise LedgerError(f"{self.key}: topic and content are required")
        if not self.date or not DATE_RE.match(self.date):
            raise LedgerError(f"{self.key}: date must be ISO YYYY-MM-DD")
        for name in ("valid_from", "valid_until"):
            value = getattr(self, name)
            if value is not None and not DATE_RE.match(value):
                raise LedgerError(f"{self.key}: {name} must be ISO or None")
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_from > self.valid_until
        ):
            raise LedgerError(f"{self.key}: valid_from after valid_until")
        if self.artifact_kind and self.artifact_kind not in ARTIFACT_KINDS:
            raise LedgerError(f"{self.key}: unknown artifact kind")
        if self.render_style not in ("crisp", "buried", "split"):
            raise LedgerError(f"{self.key}: bad render style")
        if self.kind != "decision" and self.render_style != "crisp":
            raise LedgerError(f"{self.key}: only decisions take styles")
        if self.render_style == "split" and not self.second_display_id:
            raise LedgerError(f"{self.key}: split needs second_display_id")
        if self.second_display_id and not DISPLAY_ID_RE.match(
            self.second_display_id
        ):
            raise LedgerError(f"{self.key}: bad second display id")
        if not self.scenario:
            raise LedgerError(f"{self.key}: scenario template tag required")
        if self.display_id and not DISPLAY_ID_RE.match(self.display_id):
            raise LedgerError(f"{self.key}: bad display id {self.display_id!r}")
        for edge_name in ("supersedes", "supported_by", "derived_from"):
            for ref in getattr(self, edge_name):
                if ref not in known_keys:
                    raise LedgerError(
                        f"{self.key}: {edge_name} references unknown {ref!r}"
                    )
        if self.key in self.supersedes or self.key in self.derived_from:
            raise LedgerError(f"{self.key}: self-referential edge")


@dataclass
class Ledger:
    """Validated set of hidden records for one corpus."""

    records: list[Record] = field(default_factory=list)

    def validate(self) -> "Ledger":
        keys = [r.key for r in self.records]
        if len(set(keys)) != len(keys):
            raise LedgerError("duplicate record keys")
        known = set(keys)
        for record in self.records:
            record.validate(known)
        self._check_derived_acyclic()
        self._check_display_suffixes_unique()
        return self

    def _check_derived_acyclic(self) -> None:
        edges = {r.key: list(r.derived_from) for r in self.records}
        visited: dict[str, int] = {}

        def walk(key: str, stack: list[str]) -> None:
            state = visited.get(key, 0)
            if state == 2:
                return
            if state == 1:
                raise LedgerError(f"derived_from cycle: {' -> '.join(stack + [key])}")
            visited[key] = 1
            for nxt in edges.get(key, []):
                walk(nxt, stack + [key])
            visited[key] = 2

        for key in edges:
            walk(key, [])

    def _check_display_suffixes_unique(self) -> None:
        """Global uniqueness rule: no two display IDs share a numeric suffix,
        even across prefixes. Enforced here so the generator cannot violate
        the ledger rule for parametric worlds either."""
        seen: dict[int, str] = {}
        for record in self.records:
            for did in (record.display_id, record.second_display_id):
                if not did:
                    continue
                suffix = int(did.rsplit("-", 1)[1])
                if suffix in seen and seen[suffix] != did:
                    raise LedgerError(
                        f"suffix collision: {did} vs {seen[suffix]}"
                    )
                seen[suffix] = did

    def by_key(self) -> dict[str, Record]:
        return {r.key: r for r in self.records}

    def by_topic(self, topic: str) -> list[Record]:
        return [r for r in self.records if r.topic == topic]
