"""Command line: fixtures, health, recall, trace, compare, experiments."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))

from associative_memory.config import AssociativeConfig  # noqa: E402
from associative_memory.experiments import (  # noqa: E402
    EXPERIMENTS,
    run_suite,
    save_suite,
)
from associative_memory.fixtures import (  # noqa: E402
    build_cases,
    build_graph,
    write_fixtures,
)
from associative_memory.health.checks import check_graph  # noqa: E402
from associative_memory.pipeline import STRATEGIES, AssociativeMemory  # noqa: E402

RUNS_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark" / "runs"


def _graph(args):
    if getattr(args, "graph", None):
        from associative_memory.graph.adapter import MemoryGraph

        return MemoryGraph.load(Path(args.graph))
    return build_graph()


def cmd_fixtures(args: argparse.Namespace) -> int:
    paths = write_fixtures(SOLUTION_ROOT / "fixtures" / "assoc")
    graph = build_graph()
    print(f"graph: {paths['graph']}  ({len(graph.nodes)} nodes, "
          f"{len(graph.edges)} edges)")
    print(f"cues:  {paths['cues']}  ({len(build_cases())} cases)")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    print(check_graph(_graph(args)).render(), end="")
    return 0


def cmd_recall(args: argparse.Namespace) -> int:
    graph = _graph(args)
    config = AssociativeConfig()
    memory = AssociativeMemory(
        graph=graph, config=config, strategy=args.strategy
    )
    result = memory.retrieve(args.cue)
    print(memory.explain(result, limit=args.limit))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Same cue, every strategy, side by side."""
    graph = _graph(args)
    config = AssociativeConfig()
    print(f"cue: {args.cue}\n")
    for strategy in ("seed-only",) + STRATEGIES:
        if strategy == "seed-only":
            from associative_memory.experiments import _seed_only_result

            memory = AssociativeMemory(graph=graph, config=config,
                                       strategy="spreading")
            result = _seed_only_result(memory, args.cue)
        else:
            memory = AssociativeMemory(
                graph=graph, config=config, strategy=strategy
            )
            result = memory.retrieve(args.cue)
        sources = ", ".join(result.admitted_sources()) or "(nothing admitted)"
        print(
            f"{strategy:24s} explored={len(result.explored):3d} "
            f"admitted={len(result.admitted):2d} "
            f"expansion={result.expansion_factor():5.1f} "
            f"tokens~{sum(len(s) for s in result.admitted_sources()) // 4:3d}"
        )
        print(f"{'':24s} {sources}")
    return 0


def cmd_experiments(args: argparse.Namespace) -> int:
    only = tuple(args.only) if args.only else None
    report = run_suite(only=only)
    run_id = args.run_id or (
        "ch5-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    run_dir = save_suite(report, RUNS_ROOT, run_id)
    for name, experiment in sorted(report["experiments"].items()):
        print(f"{name}: {experiment['question']}")
    print(f"\nwrote {run_dir / 'e5-suite.json'}")
    if args.print_json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """The deterministic associative-memory demonstration."""
    graph = build_graph()
    config = AssociativeConfig()
    cases = {case.case_id: case for case in build_cases()}

    print("=" * 72)
    print("Associative memory over the canonical ledger graph")
    print("=" * 72)
    print(check_graph(graph).render())

    print("-" * 72)
    print("1. The same actor, three different cues")
    print("-" * 72)
    memory = AssociativeMemory(graph=graph, config=config,
                               strategy="conditioned")
    for case_id in (
        "c-cond-silva-eventstore",
        "c-cond-silva-corpus",
        "c-cond-silva-orphans",
    ):
        case = cases[case_id]
        result = memory.retrieve(case.cue)
        print(f"\ncue: {case.cue}")
        print(f"  admitted: {', '.join(result.admitted_sources()) or '-'}")
        print(f"  ledger wants: {', '.join(case.expected_sources) or '-'}")

    print()
    print("-" * 72)
    print("2. A multi-hop pathway, with its trace")
    print("-" * 72)
    from associative_memory.pathways.trace import build_trace

    case = cases["c-hop-backup"]
    spreader = AssociativeMemory(graph=graph, config=config,
                                 strategy="spreading")
    result = spreader.retrieve(case.cue)
    print(f"\ncue: {case.cue}")
    print("seeds: " + ", ".join(
        f"{seed.node_id}({seed.score:.2f})" for seed in result.seeds
    ))
    print(
        "\nA retrieval trace records why each memory became active, not "
        "whether what it says is true.\n"
    )
    for item in result.explored:
        if item.hops < 1:
            continue
        print(build_trace(graph, result.state, item).render())
        print()
    print(f"ledger wants:  {', '.join(case.expected_sources)}")
    print(f"admitted:      {', '.join(result.admitted_sources())}")
    missed = sorted(
        set(result.explored_sources()) - set(result.admitted_sources())
    )
    print(f"reached but not admitted: {', '.join(missed) or '-'}")
    print(
        "\nThat last line is the chapter's central diagnostic: traversal "
        "and selection fail separately, and the trace says which one did."
    )

    print()
    print("-" * 72)
    print("3. Cycles terminate and budgets hold")
    print("-" * 72)
    for strategy in ("direct", "pagerank", "spreading", "conditioned"):
        runner = AssociativeMemory(graph=graph, config=config,
                                   strategy=strategy)
        result = runner.retrieve(case.cue)
        print(
            f"  {strategy:22s} explored={len(result.explored):3d} "
            f"steps={result.steps_run} stopped={result.terminated_because}"
        )

    print()
    print("-" * 72)
    print("4. What repeated retrieval does to a wrong association")
    print("-" * 72)
    from associative_memory.experiments import e5h_reinforcement_pathology

    pathology = e5h_reinforcement_pathology(graph, list(cases.values()), config)
    print(f"\ncue repeated {pathology['rounds']} times: {pathology['cue']}")
    print("the graph carries one fabricated SUPPORTED_BY edge, weight 0.60\n")
    for policy, record in pathology["policies"].items():
        track = " -> ".join(
            f"{row['false_edge_weight']:.2f}" for row in record["history"]
        )
        print(f"  {policy:16s} {track}")
        print(f"  {'':16s} health flags: "
              f"{', '.join(record['health_flags']) or 'none'}")
    print(
        "\nFrequency-driven reinforcement raises a fabricated edge toward "
        "the ceiling.\nOutcome-gated reinforcement with evidence gates "
        "lowers it. Neither removes\nthe underlying extraction error: the "
        "safeguard stops the loop, not the fault."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="associative_memory",
        description="Associative retrieval over a persistent memory graph.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fixtures = sub.add_parser("fixtures", help="write the deterministic fixture")
    fixtures.set_defaults(func=cmd_fixtures)

    health = sub.add_parser("health", help="graph and pathway diagnostics")
    health.add_argument("--graph", default=None)
    health.set_defaults(func=cmd_health)

    recall = sub.add_parser("recall", help="run one cue and show its traces")
    recall.add_argument("cue")
    recall.add_argument("--strategy", default="conditioned", choices=STRATEGIES)
    recall.add_argument("--limit", type=int, default=5)
    recall.add_argument("--graph", default=None)
    recall.set_defaults(func=cmd_recall)

    compare = sub.add_parser("compare", help="one cue across every strategy")
    compare.add_argument("cue")
    compare.add_argument("--graph", default=None)
    compare.set_defaults(func=cmd_compare)

    experiments = sub.add_parser("experiments", help="run E5-A..E5-H")
    experiments.add_argument(
        "--only", nargs="*", choices=sorted(EXPERIMENTS), default=None
    )
    experiments.add_argument("--run-id", default=None)
    experiments.add_argument("--print-json", action="store_true")
    experiments.set_defaults(func=cmd_experiments)

    demo = sub.add_parser("demo", help="deterministic demonstration")
    demo.set_defaults(func=cmd_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
