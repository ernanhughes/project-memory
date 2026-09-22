"""The control loop: run a policy until it stops, safely.

The loop is where the guards live. A sequential router that can escalate
can also cycle — retrieve, escalate, fall back, escalate again — so the
controller enforces three independent stops: a maximum action count, a
cost ceiling, and a no-repeat rule on capabilities. Each of them is
tested as the binding constraint, because a loop guard that has never
been the thing that stopped an episode has not been tested.

A one-shot policy is run through the same loop with a single step, so
that every condition in the chapter's comparison is executed by the same
code and differences between routers are differences in policy rather
than in harness.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Sequence

from ..state.model import (
    ABSTAIN,
    ASK_HUMAN,
    STOP,
    CostRecord,
    MemoryAction,
    MemoryState,
)


class RouterFailure:
    """Control-layer failure classes.

    These name failures of the *router*, and are kept separate from
    Chapter 2's failure classes, which name failures of memory and
    reasoning. A run can have a correct answer and a bad route, and the
    chapter's argument depends on being able to say so.
    """

    WRONG_CAPABILITY = "ROUTER_WRONG_CAPABILITY"
    UNDER_ROUTED = "ROUTER_UNDER_ROUTED"
    OVER_ROUTED = "ROUTER_OVER_ROUTED"
    PREMATURE_STOP = "ROUTER_PREMATURE_STOP"
    FAILED_ESCALATION = "ROUTER_FAILED_ESCALATION"
    EXCESSIVE_ESCALATION = "ROUTER_EXCESSIVE_ESCALATION"
    LOOP = "ROUTER_LOOP"
    COST_OVERRUN = "ROUTER_COST_OVERRUN"
    SCHEMA_FAILURE = "ROUTER_SCHEMA_FAILURE"
    UNAVAILABLE_CAPABILITY = "ROUTER_UNAVAILABLE_CAPABILITY"
    FEATURE_LEAKAGE = "ROUTER_FEATURE_LEAKAGE"


@dataclass
class EpisodeStep:
    step: int
    action: dict
    observation: dict | None = None
    blocked: str = ""


@dataclass
class EpisodeResult:
    """One query, routed to completion."""

    query_id: str
    policy_type: str
    policy_version: str
    steps: list[EpisodeStep] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    evidence_text: str = ""
    source_ids: list[str] = field(default_factory=list)
    retrieved_ids: list[str] = field(default_factory=list)
    terminal: str = ""
    stopped_because: str = ""
    router_failures: list[str] = field(default_factory=list)
    cost: CostRecord = field(default_factory=CostRecord)
    router_latency_ms: float = 0.0
    decision_traces: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "policy_type": self.policy_type,
            "policy_version": self.policy_version,
            "actions": list(self.actions),
            "terminal": self.terminal,
            "stopped_because": self.stopped_because,
            "router_failures": list(self.router_failures),
            "source_ids": list(self.source_ids),
            "retrieved_ids": list(self.retrieved_ids),
            "cost": self.cost.to_dict(),
            "router_latency_ms": round(self.router_latency_ms, 3),
            "steps": [
                {
                    "step": s.step,
                    "action": s.action,
                    "observation": s.observation,
                    "blocked": s.blocked,
                }
                for s in self.steps
            ],
            "decision_traces": list(self.decision_traces),
        }


class NexusController:
    """Runs one policy over one query under explicit guards."""

    def __init__(self, registry, config) -> None:
        self.registry = registry
        self.config = config

    def run(self, policy, state: MemoryState, one_shot: bool = False):
        """Execute until the policy stops or a guard fires."""
        result = EpisodeResult(
            query_id=state.query_id,
            policy_type=policy.policy_type,
            policy_version=policy.policy_version,
        )
        observations: list = []
        evidence_parts: list[str] = []
        used: list[str] = []
        current = state
        controller_config = self.config.controller

        for step in range(controller_config.max_actions):
            router_started = time.perf_counter()
            if one_shot:
                action = policy.decide(current, self.registry)
            else:
                action = policy.next_action(
                    current, observations, self.registry
                )
            result.router_latency_ms += (
                time.perf_counter() - router_started
            ) * 1000.0

            if action.capability in (STOP, ABSTAIN, ASK_HUMAN):
                result.terminal = action.capability
                result.stopped_because = action.reason or action.capability
                result.steps.append(
                    EpisodeStep(step=step, action=action.to_dict())
                )
                break

            blocked = self._blocked(action, used, result.cost)
            if blocked:
                result.router_failures.append(blocked)
                result.steps.append(
                    EpisodeStep(
                        step=step, action=action.to_dict(), blocked=blocked
                    )
                )
                result.terminal = STOP
                result.stopped_because = f"guard: {blocked}"
                break

            capability = self.registry.get(action.capability)
            execution = capability.execute(current, action)
            observation = execution.observation()
            observations.append(observation)
            used.append(action.capability)
            result.actions.append(action.capability)
            if execution.evidence_text:
                evidence_parts.append(execution.evidence_text)
            for source_id in execution.source_ids:
                if source_id not in result.source_ids:
                    result.source_ids.append(source_id)
            for source_id in execution.retrieved_ids:
                if source_id not in result.retrieved_ids:
                    result.retrieved_ids.append(source_id)
            result.cost.add(
                CostRecord(
                    latency_ms=execution.latency_ms,
                    context_tokens=execution.context_tokens,
                    model_calls=execution.model_calls,
                    graph_expansions=execution.graph_expansions,
                    cost_units=execution.cost_units,
                )
            )
            result.steps.append(
                EpisodeStep(
                    step=step,
                    action=action.to_dict(),
                    observation=observation.to_dict(),
                )
            )
            current = current.with_observation(observation)
            from .stopping import detect_disagreement

            disagrees, detail = detect_disagreement(observations)
            if disagrees:
                import dataclasses

                current = dataclasses.replace(
                    current, disagreement=True, disagreement_detail=detail
                )
            if one_shot:
                result.terminal = STOP
                result.stopped_because = "one-shot policy"
                break
        else:
            # The loop ran to its action budget without the policy electing
            # to stop. Whether that is a control failure depends on what
            # the last action returned: evidence in hand means the budget
            # merely bound the episode, no evidence means escalation ran
            # out of room before it worked.
            result.terminal = STOP
            result.stopped_because = "action-budget"
            last_had_evidence = bool(
                observations and observations[-1].evidence_count
            )
            result.router_failures.append(
                RouterFailure.EXCESSIVE_ESCALATION
                if last_had_evidence
                else RouterFailure.FAILED_ESCALATION
            )

        result.evidence_text = "\n\n---\n\n".join(evidence_parts)
        result.decision_traces = [
            trace.to_dict() for trace in policy.traces
            if trace.query_id == state.query_id
        ]
        for trace in result.decision_traces:
            if trace.get("fallback_used"):
                result.router_failures.append(RouterFailure.SCHEMA_FAILURE)
                break
        return result

    def _blocked(
        self, action: MemoryAction, used: list[str], cost: CostRecord
    ) -> str:
        controller_config = self.config.controller
        if action.capability not in self.registry:
            return RouterFailure.UNAVAILABLE_CAPABILITY
        if action.capability not in self.registry.available_ids():
            return RouterFailure.UNAVAILABLE_CAPABILITY
        if (
            controller_config.forbid_repeat_capability
            and action.capability in used
        ):
            return RouterFailure.LOOP
        from ..capabilities.adapters import COST_UNITS

        projected = cost.cost_units + COST_UNITS.get(action.capability, 1.0)
        if projected > controller_config.max_cost_units:
            return RouterFailure.COST_OVERRUN
        if cost.latency_ms > controller_config.max_latency_ms:
            return RouterFailure.COST_OVERRUN
        return ""
