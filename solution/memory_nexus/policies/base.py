"""The policy interface, and what every policy must record.

Two shapes of policy exist, and the chapter measures whether the second
is worth the extra machinery:

``MemoryPolicy``
    One-shot. Sees the situation, names one action.
``MemoryController``
    Sequential. Sees the situation *and* what earlier actions returned,
    and chooses again — including choosing to stop.

Every decision carries a ``DecisionTrace``. The trace is what makes a
routing claim checkable, and it is deliberately not a generated
rationale: the requirement is a reproducible decision state, not prose
about it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol, Sequence

from ..state.model import MemoryAction, MemoryState


@dataclass
class DecisionTrace:
    """Why the router chose what it chose, in reproducible terms."""

    query_id: str
    step: int
    policy_type: str
    policy_version: str
    state: dict = field(default_factory=dict)
    action: dict = field(default_factory=dict)
    candidates: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    decision_confidence: float = 0.0
    reason_features: list[str] = field(default_factory=list)
    fallback_used: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class MemoryPolicy(Protocol):
    """One-shot routing."""

    policy_type: str
    policy_version: str

    def decide(self, state: MemoryState, registry) -> MemoryAction:
        ...


class MemoryController(Protocol):
    """Sequential routing with observation between actions."""

    policy_type: str
    policy_version: str

    def next_action(
        self,
        state: MemoryState,
        observations: Sequence,
        registry,
    ) -> MemoryAction:
        ...


class BasePolicy:
    """Shared plumbing: trace recording and candidate filtering."""

    policy_type = "base"
    policy_version = "v0"

    def __init__(self) -> None:
        self.traces: list[DecisionTrace] = []

    def candidates(self, state: MemoryState, registry) -> list[str]:
        """Available capabilities, minus health-degraded ones.

        Health is part of routing: a stale index makes a capability a bad
        choice however well suited the question is to it. Degraded
        capabilities stay visible in the state so a trace can show that
        the router knew and declined.
        """
        available = registry.available_ids()
        if state.available_capabilities:
            allowed = set(state.available_capabilities)
            available = [cid for cid in available if cid in allowed]
        return available

    def record(
        self,
        state: MemoryState,
        action: MemoryAction,
        candidates: list[str],
        step: int = 0,
        scores: dict[str, float] | None = None,
        confidence: float = 0.0,
        reason_features: list[str] | None = None,
        fallback_used: bool = False,
        notes: str = "",
    ) -> MemoryAction:
        self.traces.append(
            DecisionTrace(
                query_id=state.query_id,
                step=step,
                policy_type=self.policy_type,
                policy_version=self.policy_version,
                state=state.to_dict(),
                action=action.to_dict(),
                candidates=list(candidates),
                scores=dict(scores or {}),
                decision_confidence=confidence,
                reason_features=list(reason_features or []),
                fallback_used=fallback_used,
                notes=notes,
            )
        )
        return action

    def manifest(self) -> dict:
        return {
            "policy_type": self.policy_type,
            "policy_version": self.policy_version,
        }
