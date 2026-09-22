"""A deterministic, offline demonstration of the control layer.

No database, no graph index, no model server. The capabilities here are
stubs with fixed behaviour, chosen so that the demonstration shows the
*mechanism* — routing, escalation, stopping, guards, traces — rather
than any result. Every number the chapter reports comes from the live
systems, not from this file.

The stub world is deliberately arranged so specialisation exists: each
stub answers some questions and not others. That makes the control loop
visible. It is not evidence that specialisation exists in the real
system; the task-by-capability matrix is what settles that.
"""

from __future__ import annotations

from .capabilities.adapters import CapabilityExecution
from .capabilities.registry import (
    ASSOCIATIVE,
    GRAPH_GLOBAL,
    GRAPH_LOCAL,
    NONE,
    RAG,
    RAW_EVIDENCE,
    build_registry,
)
from .config import NexusConfig
from .control.controller import NexusController
from .health.checks import check_nexus
from .policies.rules import RulePolicy
from .policies.sequential import SequentialPolicy
from .state.features import build_state

# Which stub answers which query, by substring. Fixed, inspectable, and
# the only "knowledge" in the demonstration.
STUB_KNOWLEDGE = {
    RAG: {"postgresql": ["adr-007.md"], "redis": ["adr-009.md"]},
    GRAPH_LOCAL: {
        "influenced": ["incident-021.md", "experiment-contention.md"],
        "connected": ["incident-021.md", "adr-007.md"],
    },
    GRAPH_GLOBAL: {
        "themes": ["adr-007.md", "adr-009.md", "commits.log"],
        "major": ["adr-007.md", "adr-009.md", "commits.log"],
    },
    ASSOCIATIVE: {
        "left behind": ["issue-041.md"],
        "untidy": ["issue-041.md"],
    },
    RAW_EVIDENCE: {"": ["adr-007.md", "session-014.md", "commits.log"]},
}

COSTS = {
    NONE: 0.0, RAG: 1.0, GRAPH_LOCAL: 3.0, GRAPH_GLOBAL: 12.0,
    ASSOCIATIVE: 1.2, RAW_EVIDENCE: 2.5,
}


def _stub(capability_id: str):
    def execute(state, action) -> CapabilityExecution:
        lowered = state.query_text.lower()
        sources: list[str] = []
        for trigger, found in STUB_KNOWLEDGE.get(capability_id, {}).items():
            if trigger == "" or trigger in lowered:
                sources = list(found)
                break
        return CapabilityExecution(
            capability_id=capability_id,
            evidence_text="; ".join(sources),
            source_ids=sources,
            retrieved_ids=sources,
            evidence_count=len(sources),
            top_score=1.0 if sources else 0.0,
            provenance_available=bool(sources),
            context_tokens=len(sources) * 40,
            latency_ms=COSTS[capability_id] * 100.0,
            cost_units=COSTS[capability_id],
            model_calls=1 if capability_id != NONE else 0,
        )

    return execute


def build_stub_registry():
    return build_registry(
        {cid: _stub(cid) for cid in COSTS}, version="nexus-demo-stubs-v0.1"
    )


QUERIES = (
    ("d1", "What event store should new services use?"),
    ("d2", "Which incidents and measurements influenced the decision?"),
    ("d3", "What major architectural themes run through this project?"),
    ("d4", "What untidy work was left behind by the measurements?"),
    ("d5", "What colour is the deployment pipeline?"),
)


def run_demo() -> int:
    config = NexusConfig()
    registry = build_stub_registry()
    controller = NexusController(registry, config)

    print("=" * 72)
    print("Memory Nexus — deterministic offline demonstration")
    print("=" * 72)
    print("Stub capabilities; no database, graph index, or model server.")
    print("Mechanism only: every reported number comes from the live runs.\n")
    print(registry.describe_all())

    print()
    print("-" * 72)
    print("1. One-shot rule routing: the decision, before anything runs")
    print("-" * 72)
    rules = RulePolicy()
    for query_id, query in QUERIES:
        state = build_state(
            query_id, query, tuple(registry.available_ids())
        )
        action = rules.decide(state, registry)
        trace = rules.traces[-1]
        signals = ", ".join(
            f"{name}={value:.2f}"
            for name, value in sorted(trace.scores.items())
            if value
        ) or "no signals"
        print(f"\n  {query}")
        print(f"    signals   {signals}")
        print(f"    selected  {action.capability} ({action.retrieval_budget})")
        print(f"    why       {action.reason}")

    print()
    print("-" * 72)
    print("2. Sequential control: observe, then choose again")
    print("-" * 72)
    episodes = []
    for query_id, query in QUERIES:
        policy = SequentialPolicy(max_actions=config.controller.max_actions)
        state = build_state(
            query_id, query, tuple(registry.available_ids())
        )
        episode = controller.run(policy, state, one_shot=False)
        episodes.append(episode)
        print(f"\n  {query}")
        for step in episode.steps:
            capability = step.action["capability"]
            if step.blocked:
                print(f"    step {step.step}: {capability} BLOCKED "
                      f"({step.blocked})")
            elif step.observation is None:
                print(f"    step {step.step}: {capability} — "
                      f"{step.action['reason']}")
            else:
                print(
                    f"    step {step.step}: {capability:<14}"
                    f"evidence={step.observation['evidence_count']} "
                    f"cost={step.observation['cost_units']}"
                )
        print(f"    terminal  {episode.terminal} "
              f"({episode.stopped_because})")
        print(f"    sources   {', '.join(episode.source_ids) or '-'}")
        print(f"    cost      {episode.cost.cost_units:.1f} units, "
              f"{episode.cost.context_tokens} tokens")

    print()
    print("-" * 72)
    print("3. Guards: a router that escalates must not cycle")
    print("-" * 72)
    loopy = SequentialPolicy(max_actions=8)
    state = build_state("d6", "unanswerable nonsense query about nothing",
                        tuple(registry.available_ids()))
    episode = controller.run(loopy, state, one_shot=False)
    print(f"  actions taken: {episode.actions}")
    print(f"  terminal:      {episode.terminal} ({episode.stopped_because})")
    print(f"  guards fired:  {episode.router_failures or 'none'}")
    print(
        "  The controller stops on the action budget, the cost ceiling, or "
        "the\n  no-repeat rule, whichever binds first."
    )

    print()
    print("-" * 72)
    print("4. Control-layer health")
    print("-" * 72)
    print(check_nexus(registry, episodes=episodes).render(), end="")
    print(
        "\nA routing trace explains why a mechanism was chosen. It is not "
        "evidence\nfor the answer: factual provenance still bottoms out in "
        "source artifacts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_demo())
