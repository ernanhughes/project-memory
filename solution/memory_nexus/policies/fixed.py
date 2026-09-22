"""Fixed and random policies: the floors every router must clear.

``FixedPolicy`` is the honest opponent. Most deployed systems are a fixed
policy that was never named as one — "we use RAG" is a routing decision
taken once, at design time, for every query. If a fixed policy matches
every router in the comparison, the chapter's answer is that the Nexus is
premature, and the chapter says so.

``RandomPolicy`` is the sanity control. A router that cannot beat
uniformly random choice among the same capabilities has learned nothing
about the situation; the random condition is what makes that visible
rather than arguable.
"""

from __future__ import annotations

import random

from ..state.model import MEDIUM, MemoryAction, MemoryState
from .base import BasePolicy


class FixedPolicy(BasePolicy):
    """Always the same capability, whatever the question."""

    policy_type = "fixed"

    def __init__(
        self,
        capability: str,
        retrieval_budget: str = MEDIUM,
        context_budget: int = 8,
    ) -> None:
        super().__init__()
        self.capability = capability
        self.retrieval_budget = retrieval_budget
        self.context_budget = context_budget
        self.policy_version = f"fixed:{capability}:v0.1"

    def decide(self, state: MemoryState, registry) -> MemoryAction:
        candidates = self.candidates(state, registry)
        action = MemoryAction(
            capability=self.capability,
            retrieval_budget=self.retrieval_budget,
            context_budget=self.context_budget,
            reason="fixed policy",
        )
        return self.record(
            state, action, candidates, confidence=1.0,
            reason_features=["fixed"],
        )


class RandomPolicy(BasePolicy):
    """Uniform choice among available capabilities. The sanity control."""

    policy_type = "random"

    def __init__(self, seed: int = 0, context_budget: int = 8) -> None:
        super().__init__()
        self.seed = seed
        self.context_budget = context_budget
        self.policy_version = f"random:seed{seed}:v0.1"
        self._rng = random.Random(seed)

    def decide(self, state: MemoryState, registry) -> MemoryAction:
        candidates = self.candidates(state, registry)
        if not candidates:
            action = MemoryAction(capability="ABSTAIN", reason="no capability")
            return self.record(state, action, candidates, fallback_used=True)
        # Deterministic given (seed, query_id): the same control run twice
        # produces the same routes, which a frozen run contract requires.
        rng = random.Random(f"{self.seed}:{state.query_id}")
        choice = rng.choice(sorted(candidates))
        action = MemoryAction(
            capability=choice,
            retrieval_budget=MEDIUM,
            context_budget=self.context_budget,
            reason="random control",
        )
        return self.record(
            state, action, candidates,
            confidence=1.0 / max(1, len(candidates)),
            reason_features=["random"],
        )
