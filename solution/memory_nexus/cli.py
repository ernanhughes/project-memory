"""Command surface for the Memory Nexus.

    python -m memory_nexus.cli capabilities
    python -m memory_nexus.cli route "Where did we decide on PostgreSQL?"
    python -m memory_nexus.cli run "..." [--policy rules|sequential|llm]
    python -m memory_nexus.cli explain RUN_ID
    python -m memory_nexus.cli health
    python -m memory_nexus.cli matrix
    python -m memory_nexus.cli evaluate [--run-id ID]
    python -m memory_nexus.cli report [--run-id ID]
    python -m memory_nexus.cli demo

``demo`` runs entirely offline against a deterministic stub registry, so
the chapter's illustration can be reproduced without a database, a graph
index, or a model server. Every other command uses the real systems.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent
INSTRUMENT_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark"
for _candidate in (str(SOLUTION_ROOT), str(INSTRUMENT_ROOT)):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from memory_nexus.config import NexusConfig  # noqa: E402
from memory_nexus.control.controller import NexusController  # noqa: E402
from memory_nexus.evaluation.regret import headroom  # noqa: E402
from memory_nexus.evaluation.runner import (  # noqa: E402
    load_matrix,
    state_builder_for,
)
from memory_nexus.evaluation.utility import Utility  # noqa: E402
from memory_nexus.experiments import run_suite, save_suite  # noqa: E402
from memory_nexus.health.checks import check_nexus  # noqa: E402
from memory_nexus.policies.fixed import FixedPolicy  # noqa: E402
from memory_nexus.policies.llm import LLMPolicy  # noqa: E402
from memory_nexus.policies.rules import RulePolicy  # noqa: E402
from memory_nexus.policies.sequential import SequentialPolicy  # noqa: E402
from memory_nexus.state.features import build_state  # noqa: E402
from memory_nexus.systems import (  # noqa: E402
    bring_up,
    build_reader,
    load_tasks,
)

RUNS_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark" / "runs"


def _setup(args):
    config = NexusConfig.from_env()
    systems, registry, report = bring_up(config)
    return config, systems, registry, report


def _state_for(query: str, registry, config, systems, query_id="adhoc"):
    linked = ()
    if systems.graph_system is not None:
        try:
            from graph_memory.evaluation.adapter import link_entities

            linked = tuple(
                link_entities(query, systems.graph_system.snapshot)
            )
        except Exception:
            linked = ()
    return build_state(
        query_id=query_id,
        query_text=query,
        available=tuple(registry.available_ids()),
        degraded=tuple(registry.degraded_ids()),
        linked_entities=linked,
        context_budget=config.context_budget,
    )


def _policy(name: str, config, registry, families=None):
    if name == "rules":
        return RulePolicy(config.context_budget), True
    if name == "sequential":
        return (
            SequentialPolicy(
                context_budget=config.context_budget,
                max_actions=config.controller.max_actions,
            ),
            False,
        )
    if name == "llm":
        return LLMPolicy(config.router_model, config.context_budget), True
    if name.startswith("fixed:"):
        return FixedPolicy(name.split(":", 1)[1]), True
    raise ValueError(f"unknown policy: {name}")


def cmd_capabilities(args) -> int:
    config, systems, registry, report = _setup(args)
    print(report.render())
    print(registry.describe_all())
    if systems.baseline:
        systems.baseline.close()
    return 0


def cmd_health(args) -> int:
    config, systems, registry, report = _setup(args)
    print(report.render())
    print(check_nexus(registry).render(), end="")
    if systems.baseline:
        systems.baseline.close()
    return 0


def cmd_route(args) -> int:
    """Show the decision without executing any memory capability."""
    config, systems, registry, _report = _setup(args)
    state = _state_for(args.query, registry, config, systems)
    policy, one_shot = _policy(args.policy, config, registry)
    action = policy.decide(state, registry) if one_shot else (
        policy.next_action(state, [], registry)
    )
    trace = policy.traces[-1]
    print(f"Query:\n  {args.query}\n")
    print("Observable state:")
    for key in (
        "interrogative", "query_tokens", "locational_signal",
        "relational_signal", "synthesis_signal", "temporal_signal",
        "causal_signal", "counterfactual_signal",
    ):
        print(f"  {key:<22} {getattr(state, key)}")
    print(f"  linked_entities        {len(state.linked_entities)} "
          f"{list(state.linked_entities)[:6]}")
    print(f"\nCandidates: {', '.join(trace.candidates)}")
    if trace.scores:
        print("Scores:")
        for name, value in sorted(trace.scores.items()):
            print(f"  {name:<22} {value}")
    print(f"\nSelected: {action.capability}")
    print(f"  budget            {action.retrieval_budget}")
    print(f"  context budget    {action.context_budget}")
    print(f"  confidence        {trace.decision_confidence}")
    print(f"  why               {action.reason}")
    print(
        "\nThis is a routing trace: it explains why this mechanism was "
        "chosen,\nnot why any resulting claim is true."
    )
    if systems.baseline:
        systems.baseline.close()
    return 0


def cmd_run(args) -> int:
    config, systems, registry, _report = _setup(args)
    reader, _generator = build_reader(config)
    state = _state_for(args.query, registry, config, systems)
    policy, one_shot = _policy(args.policy, config, registry)
    controller = NexusController(registry, config)
    episode = controller.run(policy, state, one_shot=one_shot)
    answer = reader(args.query, episode.evidence_text)
    print(f"Query:\n  {args.query}\n")
    for step in episode.steps:
        capability = step.action["capability"]
        if step.blocked:
            print(f"  step {step.step}: {capability} BLOCKED ({step.blocked})")
            continue
        if step.observation is None:
            print(f"  step {step.step}: {capability} — "
                  f"{step.action['reason']}")
            continue
        observation = step.observation
        print(
            f"  step {step.step}: {capability:<14} "
            f"evidence={observation['evidence_count']:<3} "
            f"sources={len(observation['source_ids'])} "
            f"{observation['latency_ms']:.0f}ms"
        )
        print(f"              why: {step.action['reason']}")
    print(f"\nTerminal: {episode.terminal} ({episode.stopped_because})")
    print(f"Sources:  {', '.join(episode.source_ids) or '-'}")
    print(f"Cost:     {json.dumps(episode.cost.to_dict())}")
    if episode.router_failures:
        print(f"Router failures: {', '.join(episode.router_failures)}")
    print(f"\nAnswer:\n  {answer.text}")
    run_id = args.run_id or (
        "route-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    out = RUNS_ROOT / "ch6-routes" / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = episode.to_dict()
    payload["answer"] = answer.text
    payload["policy_manifest"] = policy.manifest()
    out.write_text(json.dumps(payload, indent=2, sort_keys=True),
                   encoding="utf-8")
    print(f"\ntrace: {out}")
    if systems.baseline:
        systems.baseline.close()
    return 0


def cmd_explain(args) -> int:
    path = RUNS_ROOT / "ch6-routes" / f"{args.run_id}.json"
    if not path.exists():
        print(f"no such route trace: {path}")
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_matrix(args) -> int:
    config, systems, registry, _report = _setup(args)
    tasks, _payload, _families = load_tasks()
    matrix = load_matrix(config, registry, tasks)
    utility = Utility(config.utility)
    print(f"cells measured: {len(matrix.cells)}")
    print(f"tasks: {len(matrix.query_ids())}  "
          f"capabilities: {len(matrix.capability_ids())}")
    print()
    print(json.dumps(matrix.fixed_policy_scores(utility), indent=2,
                     sort_keys=True))
    print()
    print(json.dumps(headroom(matrix, utility), indent=2, sort_keys=True))
    if systems.baseline:
        systems.baseline.close()
    return 0


def cmd_evaluate(args) -> int:
    config, systems, registry, bring = _setup(args)
    tasks, _payload, families = load_tasks()
    matrix = load_matrix(config, registry, tasks)
    if not matrix.cells:
        print("no measured cells; run run_nexus_matrix.py first")
        return 1
    utility = Utility(config.utility)
    reader, _generator = build_reader(config)
    build_state_fn = state_builder_for(registry, config, systems.graph_system)
    measured_ids = set(matrix.query_ids())
    states = [
        build_state_fn(task) for task in tasks
        if task.task_id in measured_ids
    ]
    llm_policy = None
    if args.with_llm:
        llm_policy = LLMPolicy(config.router_model, config.context_budget)
    report = run_suite(
        matrix=matrix, utility=utility, states=states, registry=registry,
        config=config, routing_families=families, systems=systems,
        reader=reader, tasks=[t for t in tasks if t.task_id in measured_ids],
        llm_policy=llm_policy,
        include_sequential=not args.no_sequential,
    )
    report["bring_up"] = {
        "healthy": sorted(bring.healthy),
        "degraded": bring.degraded,
        "absent": bring.absent,
        "details": bring.details,
    }
    run_id = args.run_id or (
        "ch6-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    run_dir = save_suite(report, RUNS_ROOT, run_id)
    for name, experiment in sorted(report["experiments"].items()):
        print(f"{name}: {experiment['question']}")
    print(f"\nwrote {run_dir / 'e6-suite.json'}")
    if systems.baseline:
        systems.baseline.close()
    return 0


def cmd_report(args) -> int:
    path = RUNS_ROOT / args.run_id / "e6-suite.json"
    if not path.exists():
        print(f"no such suite: {path}")
        return 1
    report = json.loads(path.read_text(encoding="utf-8"))
    experiments = report["experiments"]
    print("=" * 72)
    print("E6-A  task x capability matrix")
    print("=" * 72)
    fixed = experiments["E6-A"]["fixed_policies"]
    print(f"{'capability':<16}{'quality':>9}{'evidence':>10}{'harm':>7}"
          f"{'cost':>7}{'tokens':>9}{'latency_s':>11}{'utility':>9}")
    for capability_id, record in sorted(
        fixed.items(), key=lambda item: -item[1]["utility"]
    ):
        print(
            f"{capability_id:<16}{record['quality']:>9.3f}"
            f"{record['evidence']:>10.3f}{record['harm']:>7.3f}"
            f"{record['cost_units']:>7.2f}{record['context_tokens']:>9.0f}"
            f"{record['latency_ms'] / 1000:>11.1f}{record['utility']:>9.3f}"
        )
    dominance = experiments["E6-A"]["dominance"]
    print(f"\nsingle capability dominating: "
          f"{dominance['single_capability_dominates'] or 'none'}")
    print(f"tasks where capabilities differ: "
          f"{dominance['tasks_with_a_score_difference']}"
          f"/{dominance['tasks_measured']}")
    print(f"unique wins: {json.dumps(dominance['unique_wins'])}")
    print(f"quality/cost frontier: "
          f"{experiments['E6-A']['quality_cost_frontier']}")

    print()
    print("=" * 72)
    print("E6-B  oracle headroom")
    print("=" * 72)
    print(json.dumps(experiments["E6-B"]["headroom"], indent=2,
                     sort_keys=True))

    print()
    print("=" * 72)
    print("E6-C..E  routers")
    print("=" * 72)
    routers = experiments["E6-CDE"]["routers"]
    print(f"{'router':<28}{'quality':>9}{'cost':>7}{'util':>8}"
          f"{'q-regret':>10}{'c-regret':>10}{'under':>7}{'over':>6}"
          f"{'match':>7}")
    for name, record in sorted(
        routers.items(), key=lambda item: -item[1]["totals"]["mean_utility"]
    ):
        totals = record["totals"]
        print(
            f"{name:<28}{totals['mean_quality']:>9.3f}"
            f"{totals['mean_cost_units']:>7.2f}{totals['mean_utility']:>8.3f}"
            f"{totals['mean_quality_regret']:>10.3f}"
            f"{totals['mean_cost_regret']:>10.3f}"
            f"{totals['under_routed']:>7}{totals['over_routed']:>6}"
            f"{totals['exact_oracle_match']:>7}"
        )
    if "E6-F" in experiments:
        print()
        print("=" * 72)
        print("E6-F/G  sequential control")
        print("=" * 72)
        print(json.dumps(experiments["E6-F"]["summary"], indent=2,
                         sort_keys=True))
        print(json.dumps(
            {k: v for k, v in experiments["E6-G"].items()
             if k != "records"},
            indent=2, sort_keys=True,
        ))
    return 0


def cmd_demo(args) -> int:
    from memory_nexus.demo import run_demo

    return run_demo()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory_nexus")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("capabilities", help="what the Nexus may choose")
    p.set_defaults(func=cmd_capabilities)

    p = sub.add_parser("health", help="control-layer diagnostics")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("route", help="show a routing decision only")
    p.add_argument("query")
    p.add_argument("--policy", default="rules")
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("run", help="route and execute a memory request")
    p.add_argument("query")
    p.add_argument("--policy", default="sequential")
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("explain", help="print a saved route trace")
    p.add_argument("run_id")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("matrix", help="summarise the measured matrix")
    p.set_defaults(func=cmd_matrix)

    p = sub.add_parser("evaluate", help="run E6-A..E6-G")
    p.add_argument("--run-id", default=None)
    p.add_argument("--with-llm", action="store_true")
    p.add_argument("--no-sequential", action="store_true")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("report", help="render a saved suite")
    p.add_argument("run_id")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("demo", help="offline deterministic demonstration")
    p.set_defaults(func=cmd_demo)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
