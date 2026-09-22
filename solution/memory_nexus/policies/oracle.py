"""Oracle routing: the ceiling, not a system.

The oracle reads the measured task-by-capability matrix and picks the
best cell for each task under a stated utility. It cannot be deployed —
it knows the outcome of every capability before choosing one — and its
only job is to answer the question that decides whether the rest of the
chapter is worth writing:

    How much value is available to perfect routing at all?

If the oracle matches the best fixed capability, there is no routing
problem on this benchmark and the chapter shrinks. That is a real
possible result, and the oracle is what makes it visible before any
router is built.

Two oracles are provided because they answer different questions.
``OraclePolicy`` maximises the utility. ``CheapestAdequateOracle``
picks the *cheapest* capability that reaches a quality threshold, which
is the target a cost-aware router should actually aim at — and the gap
between the two is the price of chasing the last point of quality.
"""

from __future__ import annotations

from ..state.model import MEDIUM, MemoryAction, MemoryState
from .base import BasePolicy


class OraclePolicy(BasePolicy):
    """Best measured capability per task under the configured utility."""

    policy_type = "oracle"
    policy_version = "oracle-utility-v0.1"

    def __init__(self, best_by_query: dict[str, str], context_budget: int = 8):
        super().__init__()
        self.best_by_query = best_by_query
        self.context_budget = context_budget

    def decide(self, state: MemoryState, registry) -> MemoryAction:
        candidates = self.candidates(state, registry)
        choice = self.best_by_query.get(state.query_id)
        fallback = choice is None or choice not in candidates
        if fallback:
            choice = registry.cheapest(candidates) or "ABSTAIN"
        action = MemoryAction(
            capability=choice,
            retrieval_budget=MEDIUM,
            context_budget=self.context_budget,
            reason="oracle: measured best cell",
        )
        return self.record(
            state, action, candidates, confidence=1.0,
            reason_features=["oracle"], fallback_used=fallback,
            notes="upper bound; not deployable",
        )


class CheapestAdequateOracle(BasePolicy):
    """Cheapest capability that reaches the quality threshold."""

    policy_type = "oracle-cheapest-adequate"
    policy_version = "oracle-cheapest-v0.1"

    def __init__(
        self, choice_by_query: dict[str, str], context_budget: int = 8
    ):
        super().__init__()
        self.choice_by_query = choice_by_query
        self.context_budget = context_budget

    def decide(self, state: MemoryState, registry) -> MemoryAction:
        candidates = self.candidates(state, registry)
        choice = self.choice_by_query.get(state.query_id)
        fallback = choice is None or choice not in candidates
        if fallback:
            choice = registry.cheapest(candidates) or "ABSTAIN"
        action = MemoryAction(
            capability=choice,
            retrieval_budget=MEDIUM,
            context_budget=self.context_budget,
            reason="oracle: cheapest capability meeting the threshold",
        )
        return self.record(
            state, action, candidates, confidence=1.0,
            reason_features=["oracle-cheapest"], fallback_used=fallback,
            notes="upper bound for cost-aware routing; not deployable",
        )


def best_by_utility(matrix, utility) -> dict[str, str]:
    """Per task, the capability with the highest utility in the matrix."""
    choices: dict[str, str] = {}
    for query_id, cells in matrix.by_query().items():
        scored = [
            (utility.score(cell), cell.capability_id)
            for cell in cells
            if cell.measured
        ]
        if scored:
            choices[query_id] = max(scored, key=lambda item: (item[0], item[1]))[1]
    return choices


def cheapest_adequate(matrix, threshold: float, utility) -> dict[str, str]:
    """Per task, the cheapest capability whose quality clears ``threshold``.

    Ties on cost break toward the higher quality; if nothing clears the
    threshold the best available quality is taken, so the oracle never
    abstains on the benchmark's behalf.
    """
    choices: dict[str, str] = {}
    for query_id, cells in matrix.by_query().items():
        measured = [cell for cell in cells if cell.measured]
        if not measured:
            continue
        adequate = [
            cell for cell in measured if utility.quality(cell) >= threshold
        ]
        pool = adequate or measured
        choices[query_id] = min(
            pool,
            key=lambda cell: (
                cell.cost_units,
                -utility.quality(cell),
                cell.capability_id,
            ),
        ).capability_id
    return choices
