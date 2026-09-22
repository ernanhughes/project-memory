"""Inspection surface for the context-frames layer.

    python -m context_frames.cli demo
    python -m context_frames.cli project --project memory-book
    python -m context_frames.cli build --task T1-architecture --condition C6
    python -m context_frames.cli why --task T1-architecture --unit mb-method-earn
    python -m context_frames.cli rejected --task T1-architecture
    python -m context_frames.cli ladder
    python -m context_frames.cli backtest

Every command reads the same frozen fixtures the suite uses, so what the
terminal prints is what the run recorded.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import fixtures as fx
from . import metrics as M
from .backtest import backtest
from .experiments import Harness
from .policy import LADDER

BAR = "=" * 72


def _harness(args) -> Harness:
    return Harness(budget=args.budget, use_embeddings=not args.no_embeddings)


def cmd_demo(args) -> int:
    h = _harness(args)
    pub, arch = fx.T1_PUBLICATION(), fx.T1_ARCHITECTURE()
    print(BAR)
    print("SAME CORPUS.  SAME QUERY.  SAME MODEL.  SAME BUDGET.")
    print(BAR)
    print(f"\nQuery:\n  {pub.query}\n")
    print(f"Budget: {h.budget} estimated tokens    "
          f"Corpus: {len(h.units_list)} units, 3 projects")
    print(f"Retriever: {h.retriever.describe()}\n")

    for task, heading in ((pub, "WORK FRAME A"), (arch, "WORK FRAME B")):
        work = task.work_frame
        print(BAR)
        print(f"{heading}  ({work.work_frame_id})")
        print(f"  objective: {work.objective}")
        print(f"  work type: {work.work_type}")
        print(f"  signals  : "
              + ", ".join(f"{s.signal_id}({s.kind})" for s in work.signals))
        for condition, title in (("C0", "STRONG RAG (query only)"),
                                 ("C6", "FRAME-CONDITIONED CONTEXT")):
            scored, bundle, _ = h.score(condition, task)
            print(f"\n  {title}")
            for i, item in enumerate(bundle.items[:8], start=1):
                label = task.label(item.members[0])
                print(f"    {i:>2}. {item.members[0]:<32} "
                      f"[{item.kind}] {label}")
            if len(bundle.items) > 8:
                print(f"        ... {len(bundle.items) - 8} more")
            print(f"    must-include recall {scored['must_include_recall']:.2f}"
                  f"   context precision {scored['context_precision']:.2f}"
                  f"   distractors {scored['distractor_admission']:.2f}"
                  f"   tokens {scored['bundle_tokens']}")
        print()

    print(BAR)
    print("DID THE GOAL CHANGE THE CONTEXT?")
    print(BAR)
    for condition in ("C0", "C6"):
        _, b_pub, _ = h.score(condition, pub)
        _, b_arch, _ = h.score(condition, arch)
        divergence = M.bundle_divergence(b_pub, b_arch)
        verdict = ("identical bundles" if divergence["jaccard"] == 1.0
                   else f"{len(divergence['shared'])} of "
                        f"{len(set(b_pub.unit_ids()) | set(b_arch.unit_ids()))}"
                        f" units shared")
        print(f"  {condition}: overlap {divergence['jaccard']:.4f}   {verdict}")
    print()
    return 0


def cmd_project(args) -> int:
    frame = fx.PROJECT_FRAMES[args.project]()
    print(json.dumps(frame.to_dict(), indent=2))
    return 0


def cmd_build(args) -> int:
    h = _harness(args)
    task = fx.task_by_id(args.task)
    scored, bundle, trace = h.score(args.condition, task)
    print(f"bundle {bundle.bundle_id}  digest {bundle.digest()}  "
          f"{bundle.tokens}/{bundle.budget_tokens} estimated tokens")
    print(f"work frame {trace.work_frame} / project frame {trace.project_frame}"
          f" / policy {trace.policy_version}\n")
    for i, item in enumerate(bundle.items, start=1):
        print(f"{i:>2}. {item.item_id}  [{item.kind}]  {item.tokens} tokens")
        print(f"    members: {', '.join(item.members)}")
        print(f"    sources: {', '.join(item.source_refs) or 'unsourced'}")
        if item.temporal_note:
            print(f"    temporal: {item.temporal_note}")
        if item.conflict_with:
            print(f"    disagrees with: {', '.join(item.conflict_with)}")
    print("\nmetrics:", json.dumps(scored, indent=2))
    if args.render:
        print("\n" + BAR + "\nRENDERED CONTEXT\n" + BAR)
        print(bundle.render())
    return 0


def cmd_why(args) -> int:
    h = _harness(args)
    task = fx.task_by_id(args.task)
    _, _, trace = h.score(args.condition, task)
    record = trace.why(args.unit)
    if record is None:
        print(f"{args.unit} was never a candidate under {args.condition}: "
              f"retrieval never surfaced it (E1).")
        return 1
    print(json.dumps(record, indent=2))
    return 0


def cmd_rejected(args) -> int:
    h = _harness(args)
    task = fx.task_by_id(args.task)
    _, bundle, trace = h.score(args.condition, task)
    print(f"{len(trace.rejected())} rejected of {len(trace.candidates)} "
          f"candidates\n")
    for candidate in trace.rejected():
        codes = ", ".join(c for c in candidate.reason_codes
                          if not c.startswith("CLASS_TIER_"))
        print(f"  {candidate.unit_id:<34} q={candidate.signals.query_relevance:.2f}"
              f" goal={candidate.signals.goal_relevance:.2f}"
              f"  {codes}")
    print("\nfailure attribution:",
          json.dumps(M.attribute_failure(task, bundle, trace), indent=2))
    return 0


def cmd_ladder(args) -> int:
    h = _harness(args)
    header = ("condition", "must", "useful", "prec", "distract", "harm",
              "leak", "tokens")
    print(f"{header[0]:<22}" + "".join(f"{c:>10}" for c in header[1:]))
    for condition in list(LADDER) + [None]:
        name = condition.name if condition else "CO"
        label = condition.label if condition else "ledger oracle ceiling"
        rows = [h.score(name, task)[0] for task in fx.all_tasks()]
        n = len(rows)

        def mean(key: str) -> float:
            return sum(r[key] for r in rows) / n

        print(f"{name} {label:<19}"
              f"{mean('must_include_recall'):>10.3f}"
              f"{mean('useful_recall'):>10.3f}"
              f"{mean('context_precision'):>10.3f}"
              f"{mean('distractor_admission'):>10.3f}"
              f"{mean('harmful_admission'):>10.3f}"
              f"{mean('cross_project_leakage'):>10.3f}"
              f"{mean('bundle_tokens'):>10.0f}")
    return 0


def cmd_backtest(args) -> int:
    h = _harness(args)
    result = backtest(h, fx.PF_MEMORY_BOOK())
    print(f"base {result['base_frame']}  primary {result['primary_metric']}")
    print(f"baseline {json.dumps(result['baseline'])}\n")
    for proposal in result["proposals"]:
        print(f"{proposal['decision']:<8} {proposal['proposal']:<32}"
              f" delta {proposal['primary_delta']:+.4f}")
        print(f"         {proposal['rationale']}")
        if proposal["gate_breaches"]:
            print(f"         gates: {'; '.join(proposal['gate_breaches'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="context_frames")
    parser.add_argument("--budget", type=int, default=1500)
    parser.add_argument("--no-embeddings", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo").set_defaults(func=cmd_demo)

    p = sub.add_parser("project")
    p.add_argument("--project", default="memory-book")
    p.set_defaults(func=cmd_project)

    p = sub.add_parser("build")
    p.add_argument("--task", default="T1-architecture")
    p.add_argument("--condition", default="C6")
    p.add_argument("--render", action="store_true")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("why")
    p.add_argument("--task", default="T1-architecture")
    p.add_argument("--condition", default="C6")
    p.add_argument("--unit", required=True)
    p.set_defaults(func=cmd_why)

    p = sub.add_parser("rejected")
    p.add_argument("--task", default="T1-architecture")
    p.add_argument("--condition", default="C6")
    p.set_defaults(func=cmd_rejected)

    sub.add_parser("ladder").set_defaults(func=cmd_ladder)
    sub.add_parser("backtest").set_defaults(func=cmd_backtest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
