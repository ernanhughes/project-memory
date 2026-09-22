"""The hand-authored router: the minimum viable Nexus.

Every rule here is a hypothesis stated in code, readable in one sitting,
and falsifiable by the task-by-capability matrix. If the matrix says a
rule routes to a capability that does not in fact win those tasks, the
rule is wrong and the chapter reports it rather than quietly retuning.

The rules read **only the query text**. That constraint is the whole
point. Chapter 4's routing prototype keyed on the evaluator's task family
— a field that exists only because a human labelled the benchmark — and
a router with access to it is being told what kind of question it faces
rather than working it out. That version is kept here as
``LeakyFamilyPolicy``, clearly labelled, so the chapter can measure
exactly what the leaked label is worth.
"""

from __future__ import annotations

from ..capabilities.registry import (
    ASSOCIATIVE,
    GRAPH_GLOBAL,
    GRAPH_LOCAL,
    NONE,
    RAG,
)
from ..state.model import HIGH, LOW, MEDIUM, MemoryAction, MemoryState
from .base import BasePolicy

# Threshold above which a signal counts as present. Deliberately low: the
# signals are normalised shares of a short question's content words, so a
# single matching term in a ten-word question scores 0.1.
SIGNAL_ON = 0.12


class RulePolicy(BasePolicy):
    """Transparent routing from lexical signals in the query."""

    policy_type = "rules"
    policy_version = "rules-v0.1"

    def __init__(self, context_budget: int = 8) -> None:
        super().__init__()
        self.context_budget = context_budget

    def decide(self, state: MemoryState, registry) -> MemoryAction:
        candidates = self.candidates(state, registry)
        reasons: list[str] = []
        scores = {
            "locational": state.locational_signal,
            "relational": state.relational_signal,
            "synthesis": state.synthesis_signal,
            "temporal": state.temporal_signal,
            "causal": state.causal_signal,
            "counterfactual": state.counterfactual_signal,
        }

        def choose(capability: str, why: str, budget: str = MEDIUM):
            reasons.append(why)
            preferred = capability if capability in candidates else RAG
            if preferred != capability:
                reasons.append(f"{capability} unavailable; fell back to RAG")
            action = MemoryAction(
                capability=preferred,
                retrieval_budget=budget,
                context_budget=self.context_budget,
                reason="; ".join(reasons),
            )
            return self.record(
                state, action, candidates, scores=scores, confidence=0.6,
                reason_features=reasons,
                fallback_used=preferred != capability,
            )

        # Order matters and is stated, not implicit. Corpus-wide synthesis
        # first because it is the one class plain retrieval cannot reach
        # at any budget; the cheapest adequate capability last.
        if state.synthesis_signal >= SIGNAL_ON:
            return choose(
                GRAPH_GLOBAL, "corpus-wide synthesis wording", HIGH
            )
        if state.relational_signal >= SIGNAL_ON:
            return choose(
                GRAPH_LOCAL, "relational wording between entities"
            )
        if state.causal_signal >= SIGNAL_ON and len(state.linked_entities) >= 2:
            return choose(
                ASSOCIATIVE,
                "causal wording with several linked entities: evidence may "
                "be a chain away",
            )
        # Choosing no memory needs an explicit signal, not a short
        # question. An earlier version fired on length alone and routed
        # ordinary project questions to no memory at all; detecting that
        # history is irrelevant from wording is largely unsolved, so the
        # rule is deliberately narrow and the chapter reports what that
        # narrowness costs.
        if state.generality_signal >= 1.0 and not state.linked_entities:
            return choose(
                NONE,
                "the question explicitly disclaims this project's history",
                LOW,
            )
        return choose(RAG, "default: cheapest capability with provenance")


class LeakyFamilyPolicy(BasePolicy):
    """Routes on the evaluator's task family. A control, never a system.

    This is the Chapter 4 routing table, promoted to a full capability
    router. It is included to quantify one thing: how much of any routing
    gain comes from knowing what *kind* of question this is — a label a
    deployed system does not have. Its score is an upper bound on
    query-classification routing, not a result the Nexus may claim.
    """

    policy_type = "leaky-family"
    policy_version = "leaky-family-v0.1"

    TABLE = {
        "locate": RAG,
        "decision": RAG,
        "provenance": GRAPH_LOCAL,
        "temporal": RAG,
        "use": RAG,
        "relational": GRAPH_LOCAL,
        "global": GRAPH_GLOBAL,
        "indirect": ASSOCIATIVE,
        "no-memory": NONE,
    }

    def __init__(self, families: dict[str, str], context_budget: int = 8):
        super().__init__()
        self.families = families
        self.context_budget = context_budget

    def decide(self, state: MemoryState, registry) -> MemoryAction:
        candidates = self.candidates(state, registry)
        family = self.families.get(state.query_id, "")
        capability = self.TABLE.get(family, RAG)
        if capability not in candidates:
            capability = RAG
        action = MemoryAction(
            capability=capability,
            retrieval_budget=HIGH if capability == GRAPH_GLOBAL else MEDIUM,
            context_budget=self.context_budget,
            reason=f"ledger family={family!r} (leaked label)",
        )
        return self.record(
            state, action, candidates, confidence=0.9,
            reason_features=[f"family={family}", "LEAKED-LABEL"],
            notes="control condition: uses evaluator metadata",
        )
