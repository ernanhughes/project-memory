"""Observe, then choose again: the cheapest-first escalation ladder.

One-shot routing has to predict which capability a question needs before
seeing any evidence. Sequential control does not: it can start with the
cheapest capability that might work, look at what came back, and escalate
only when the diagnostics say the cheap answer is not good enough.

The policy is deterministic and hand-written. That is deliberate — if a
policy this simple captures most of the oracle's headroom, the chapter's
answer about learned routing is that it has not been earned.

The escalation ladder:

    cheapest capability with provenance
      ↓ evidence returned and settled?  → stop
      ↓ no evidence, corpus-wide wording → corpus-wide synthesis
      ↓ no evidence, entity links present → entity-centred graph search
      ↓ no evidence, otherwise            → associative activation
      ↓ still nothing, or capabilities disagree → raw evidence
      ↓ raw evidence empty                → abstain
"""

from __future__ import annotations

from typing import Sequence

from ..capabilities.registry import (
    ASSOCIATIVE,
    GRAPH_GLOBAL,
    GRAPH_LOCAL,
    RAG,
    RAW_EVIDENCE,
)
from ..control.stopping import StopConfig, detect_disagreement, should_stop
from ..state.model import (
    ABSTAIN,
    HIGH,
    MEDIUM,
    STOP,
    MemoryAction,
    MemoryState,
)
from .base import BasePolicy
from .rules import SIGNAL_ON


class SequentialPolicy(BasePolicy):
    """Cheapest-first control with diagnostics-driven escalation."""

    policy_type = "sequential"
    policy_version = "sequential-v0.1"

    def __init__(
        self,
        context_budget: int = 8,
        stop_config: StopConfig | None = None,
        max_actions: int = 3,
    ) -> None:
        super().__init__()
        self.context_budget = context_budget
        self.stop_config = stop_config or StopConfig()
        self.max_actions = max_actions

    def next_action(
        self, state: MemoryState, observations: Sequence, registry
    ) -> MemoryAction:
        candidates = self.candidates(state, registry)
        step = len(observations)
        used = {observation.capability_id for observation in observations}

        def emit(capability, why, budget=MEDIUM, confidence=0.6,
                 features=None):
            preferred = capability
            fallback = False
            if capability not in candidates and capability not in (
                STOP, ABSTAIN
            ):
                preferred = registry.cheapest(
                    [c for c in candidates if c not in used]
                ) or ABSTAIN
                fallback = True
            action = MemoryAction(
                capability=preferred,
                retrieval_budget=budget,
                context_budget=self.context_budget,
                require_provenance=self.stop_config.require_provenance,
                reason=why,
            )
            return self.record(
                state, action, candidates, step=step, confidence=confidence,
                reason_features=features or [why], fallback_used=fallback,
            )

        # Step 0: the cheapest capability that can produce provenance.
        if not observations:
            first = RAG if RAG in candidates else registry.cheapest(candidates)
            return emit(
                first, "start with the cheapest capability with provenance",
                confidence=0.5, features=["cheapest-first"],
            )

        budget_exhausted = step >= self.max_actions
        decision = should_stop(
            observations, self.stop_config, budget_exhausted
        )
        if decision.stop:
            return emit(
                STOP, f"stop: {decision.reason}", confidence=0.8,
                features=[f"stop:{decision.reason}"]
                + [f"{k}={v}" for k, v in decision.signals.items()],
            )

        # Disagreement between what has run so far is a reason to look at
        # raw evidence, not a reason to pick a side. Resolving the
        # contradiction belongs to a later chapter.
        disagrees, detail = detect_disagreement(observations)
        if disagrees and RAW_EVIDENCE not in used:
            return emit(
                RAW_EVIDENCE,
                f"capabilities disagree ({detail}); fall back to raw sources",
                HIGH, confidence=0.7, features=["disagreement", detail],
            )

        # Escalate on what the question looks like, now that the cheap
        # attempt has failed to settle it.
        if state.synthesis_signal >= SIGNAL_ON and GRAPH_GLOBAL not in used:
            return emit(
                GRAPH_GLOBAL,
                "cheap retrieval unsettled and the wording is corpus-wide",
                HIGH, confidence=0.6, features=["escalate:synthesis"],
            )
        entity_route = (
            state.linked_entities
            or state.relational_signal >= SIGNAL_ON
            or state.causal_signal >= SIGNAL_ON
        )
        if entity_route and GRAPH_LOCAL not in used:
            why = (
                "links to graph entities" if state.linked_entities
                else "relational or causal wording"
            )
            return emit(
                GRAPH_LOCAL,
                f"cheap retrieval unsettled and the question has {why}",
                confidence=0.6, features=["escalate:entities", why],
            )
        if ASSOCIATIVE not in used:
            return emit(
                ASSOCIATIVE,
                "cheap retrieval unsettled; evidence may be a chain away",
                confidence=0.5, features=["escalate:indirect"],
            )
        if RAW_EVIDENCE not in used:
            return emit(
                RAW_EVIDENCE, "derived memory unsettled; fall back to raw "
                "sources", HIGH, confidence=0.5, features=["fallback:raw"],
            )
        return emit(
            ABSTAIN,
            "no capability produced sufficient evidence",
            confidence=0.4, features=["abstain"],
        )
