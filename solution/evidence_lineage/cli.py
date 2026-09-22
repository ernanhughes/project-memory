"""Evidence-lineage CLI.

    python -m evidence_lineage.cli claims "PostgreSQL was selected because ..."
    python -m evidence_lineage.cli explain claim-main
    python -m evidence_lineage.cli trace claim-main
    python -m evidence_lineage.cli support claim-main
    python -m evidence_lineage.cli sources claim-main
    python -m evidence_lineage.cli dependents s19-benchmark
    python -m evidence_lineage.cli verify claim-14pct
    python -m evidence_lineage.cli graph claim-main
    python -m evidence_lineage.cli impact s19-benchmark
    python -m evidence_lineage.cli evaluate [--run-id ID]
    python -m evidence_lineage.cli report RUN_ID
    python -m evidence_lineage.cli health
    python -m evidence_lineage.cli demo
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent
for _candidate in (str(SOLUTION_ROOT),):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from evidence_lineage import claims as claim_mod  # noqa: E402
from evidence_lineage.config import EvidenceConfig  # noqa: E402
from evidence_lineage.evidence import claim_support_status  # noqa: E402
from evidence_lineage.experiments import run_suite  # noqa: E402
from evidence_lineage import fixtures as fx  # noqa: E402
from evidence_lineage.health import check_layer  # noqa: E402
from evidence_lineage.revision import impact_of  # noqa: E402
from evidence_lineage.verification import verify_backward  # noqa: E402

RUNS_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark" / "runs"


def _context():
    return fx.build_graph(), fx.build_supports()


def cmd_claims(args) -> int:
    fn = {"c0": claim_mod.extract_claims_c0,
          "c1": claim_mod.extract_claims_c1,
          "c2": claim_mod.extract_claims_c2}[args.extractor]
    found = fn(args.text, artifact="adhoc")
    for claim in found:
        flag = " [abstained]" if claim.abstained else ""
        print(f"  {claim.id}: {claim.text}{flag}")
    print(claim_mod.extraction_report(found))
    return 0


def cmd_explain(args) -> int:
    graph, supports = _context()
    claim_id = args.claim_id
    support = supports.get(claim_id)
    if support is None:
        print(f"unknown claim: {claim_id}")
        return 1
    status = claim_support_status(support, fx.ENTAILS)
    node = graph.nodes[claim_id]
    print(f"Claim:\n  {node.label}\n")
    for group in support.groups:
        state = status["group_states"][group.id]
        mark = "ok" if state == "satisfied" else state
        print(f"Support group {group.id} [{mark}]:")
        for member in group.members:
            span = graph.nodes[member]
            print(f"  [{mark}] {member} — {span.label}")
    derived = graph.lineage_of(claim_id)
    if derived:
        print("Derived from:")
        for edge in derived:
            print(f"  {edge.target}")
    trace = graph.trace_to_sources(claim_id)
    print(f"\nOriginal spans: {', '.join(trace['grounded_spans']) or '-'}")
    if trace["open_lineages"]:
        print(f"Open lineages: {', '.join(trace['open_lineages'])}")
    retrieval = graph.retrieval_traces.get(claim_id)
    control = graph.control_traces.get(claim_id)
    if retrieval:
        print(f"\nRetrieval causality (why recalled): "
              f"{' -> '.join(retrieval)}")
    if control:
        print(f"Control causality (why this process): "
              f"{' -> '.join(control)}")
    print("\nNeither trace above is evidential support.")
    return 0


def cmd_trace(args) -> int:
    graph, _ = _context()
    print(json.dumps(graph.trace_to_sources(args.claim_id), indent=2))
    return 0


def cmd_support(args) -> int:
    _, supports = _context()
    support = supports.get(args.claim_id)
    if support is None:
        print(f"unknown claim: {args.claim_id}")
        return 1
    print(json.dumps(claim_support_status(support, fx.ENTAILS), indent=2))
    return 0


def cmd_sources(args) -> int:
    graph, _ = _context()
    print(json.dumps(graph.sources_for(args.claim_id), indent=2))
    return 0


def cmd_dependents(args) -> int:
    graph, _ = _context()
    print(json.dumps(graph.dependents_of(args.source_id), indent=2))
    return 0


def cmd_verify(args) -> int:
    stage_truth = fx.STAGE_SUPPORT.get(args.claim_id)
    if stage_truth is None:
        print(f"no stage fixture for: {args.claim_id}")
        return 1
    verification = verify_backward(args.claim_id, dict(stage_truth))
    print(json.dumps(verification.to_dict(), indent=2))
    return 0


def cmd_graph(args) -> int:
    graph, _ = _context()
    trace = graph.trace_to_sources(args.claim_id)
    print(f"claim {args.claim_id}")
    for step in trace["trail"]:
        target = f" -> {step['target']}" if "target" in step else ""
        print(f"  depth {step['depth']}: {step['node']} "
              f"[{step['relation']}{target}]")
    return 0


def cmd_impact(args) -> int:
    graph, supports = _context()
    report = impact_of(graph, supports, fx.ENTAILS, args.source_id)
    print(json.dumps(report.to_dict(), indent=2))
    if report.affected_claims:
        print("\nThese derived claims depend on "
              f"{args.source_id} and require reevaluation:")
        for claim in report.affected_claims:
            print(f"  {claim}")
    return 0


def cmd_evaluate(args) -> int:
    config = EvidenceConfig()
    report = run_suite(config)
    run_id = args.run_id or ("ch7-" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"))
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "e7-suite.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    for name, experiment in sorted(report["experiments"].items()):
        print(f"{name}: {experiment['question']}")
    print(f"\nwrote {run_dir / 'e7-suite.json'}")
    return 0


def cmd_report(args) -> int:
    path = RUNS_ROOT / args.run_id / "e7-suite.json"
    if not path.exists():
        print(f"no such suite: {path}")
        return 1
    report = json.loads(path.read_text(encoding="utf-8"))
    exps = report["experiments"]
    print("E7-A pointer vs support:")
    for level, record in exps["E7-A"]["results"].items():
        overall = record["overall"]
        print(f"  {level:<12} precision={overall['support_precision']:.3f} "
              f"coverage={overall['support_coverage']:.3f}")
    print("E7-B extraction coverage:",
          {k: round(v["coverage"], 3)
           for k, v in exps["E7-B"]["results"].items()})
    print("E7-C group validity:", exps["E7-C"]["group_validity"])
    print("E7-D echo recall @0.55:",
          [r for r in exps["E7-D"]["threshold_sweep"]
           if r["threshold"] == 0.55][0]["recall"])
    print("E7-F completeness:", exps["E7-F"]["completeness"])
    print("E7-G localisation:", exps["E7-G"]["scores"])
    print("E7-H s19 impact:", exps["E7-H"]["s19_impact"])
    print("E7-H a07 impact:", exps["E7-H"]["a07_impact"])
    print("E7-I claim-main after s44 removal:",
          exps["E7-I"]["claim_main_after"])
    print("E7-J divergence:", exps["E7-J"]["cells"])
    print("costs:", report["costs"])
    return 0


def cmd_health(args) -> int:
    graph, _ = _context()
    print(check_layer(graph)["render"])
    return 0


def cmd_demo(args) -> int:
    graph, supports = _context()
    print("Claim:")
    print(f"  {graph.nodes['claim-main'].label}\n")
    status = claim_support_status(supports["claim-main"], fx.ENTAILS)
    print(f"Status: {status['status']} "
          f"(groups: {status['satisfied_groups']})\n")
    verification = verify_backward(
        "claim-14pct", dict(fx.STAGE_SUPPORT["claim-14pct"]))
    print(f"Hallucination case claim-14pct: "
          f"{verification.final_verdict}, "
          f"first failure at stage '{verification.error_stage}'")
    report = impact_of(graph, supports, fx.ENTAILS, "a07-rationale")
    print(f"Withdrawing a07-rationale affects: "
          f"{report.affected_claims or 'none'}")
    print("\nRaw-source termination guarantees inspectability and "
          "historical grounding, not truth.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence_lineage")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("claims", help="extract checkable claims")
    p.add_argument("text")
    p.add_argument("--extractor", default="c2", choices=("c0", "c1", "c2"))
    p.set_defaults(func=cmd_claims)

    for name, help_text, func, arg in (
            ("explain", "evidence-based explanation", cmd_explain,
             "claim_id"),
            ("trace", "trace claim to sources", cmd_trace, "claim_id"),
            ("support", "support groups for a claim", cmd_support,
             "claim_id"),
            ("sources", "grounding spans for a claim", cmd_sources,
             "claim_id"),
            ("dependents", "claims depending on a source", cmd_dependents,
             "source_id"),
            ("verify", "reverse verification of a claim", cmd_verify,
             "claim_id"),
            ("graph", "render the dependency trail", cmd_graph,
             "claim_id"),
            ("impact", "dependency impact of withdrawing evidence",
             cmd_impact, "source_id")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument(arg)
        p.set_defaults(func=func)

    p = sub.add_parser("evaluate", help="run E7-A..E7-J")
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("report", help="render a saved suite")
    p.add_argument("run_id")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("health", help="structural health")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("demo", help="offline deterministic demonstration")
    p.set_defaults(func=cmd_demo)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
