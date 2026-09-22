"""CLI for the temporal-memory demo and experiments.

Commands: demo, permutations, trajectory, query, replay, health, benchmark.
Multi-process manual commands (broker/recorder/publish) are served by
`demo --live` in-process here; see README for the manual sequence.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import fixtures as fx
from .config import TemporalConfig
from .experiments import freeze, run_suite
from .health import health_report
from .log import EventLog
from .metrics import score_suite
from .model import EventEnvelope
from .ordering import temporal_sort
from .query import MaterializedProjection, ResolverCondition, TemporalEngine
from .reducer import projection_digest, replay


def cmd_demo(args) -> int:
    live = args.live
    if live:
        from .experiments import exp_e8d_arrival_disorder
        d = exp_e8d_arrival_disorder(use_live_transport=True)
        print("SEMANTIC ORDER:", " -> ".join(d["semantic_order"]))
        print("ARRIVAL ORDER: ", " -> ".join(d["arrival_order"]))
        print("RESOLVED ORDER:", " -> ".join(d["resolved_temporal_order"]))
        print("arrival-resolver:", d["arrival_resolver"])
        print("temporal-resolver:", d["temporal_resolver"])
        return 0
    order, plan = fx.arrival_disorder_plan()
    ingest = [order[2], order[0], order[1]]  # C, A, B arrival
    log = freeze(ingest)
    print("SEMANTIC ORDER:", " -> ".join(e.event_id for e in order))
    print("ARRIVAL ORDER: ", " -> ".join(log.arrival_order()))
    print("RESOLVED ORDER:", " -> ".join(log.event_time_order()))
    for cond in ("T0-bag", "T1-arrival", "T1b-event-time",
                 "T2-ordered", "T3-temporal"):
        ans = TemporalEngine(log, cond).current(fx.SUBJECT_BACKEND)
        print(f"{cond:15} -> {ans.value} [{ans.status}] {ans.detail}")
    print("\nTRAJECTORY:")
    for row in TemporalEngine(log, "T3-temporal").history(fx.SUBJECT_BACKEND):
        print(f"  {row['before']} --{row['type']}/{row['event']}--> {row['after']}")
    return 0


def cmd_permutations(_args) -> int:
    from .experiments import exp_e8b_sensitive, exp_e8c_invariant
    b = exp_e8b_sensitive()
    print("ORDER-SENSITIVE (benchmark/decision swap):")
    print("  canonical MOTIVATED_BY admissible:", b["canonical_motivated_admissible"])
    print("  permuted  MOTIVATED_BY admissible:", b["permuted_motivated_admissible"])
    print("  expected change: yes; observed change:",
          b["canonical_motivated_admissible"] != b["permuted_motivated_admissible"],
          "->", "PASS" if b["pass"] else "FAIL")
    c = exp_e8c_invariant()
    print("ORDER-INVARIANT (independent swap):")
    for subject, row in c["rows"].items():
        stable = row["stable"]["T3-temporal"]
        print(f"  {subject}: stable={stable} ->",
              "PASS" if stable else "FAIL")
    return 0


def cmd_trajectory(args) -> int:
    subject = args.subject or fx.SUBJECT_BACKEND
    log = freeze(fx.canonical_migration())
    for row in TemporalEngine(log, "T3-temporal").history(subject):
        print(f"{row['before']}")
        print(f"   | {row['event']} ({row['type']})")
        print("   v")
    eng = TemporalEngine(log, "T3-temporal")
    print(eng.current(subject).value)
    return 0


def cmd_query(args) -> int:
    log = freeze(fx.canonical_migration())
    eng = TemporalEngine(log, args.condition)
    if args.valid_at and args.known_at:
        ans = eng.bitemporal(args.subject, args.valid_at, args.known_at)
    elif args.valid_at:
        ans = eng.at(args.subject, args.valid_at)
    elif args.known_at:
        ans = eng.as_known(args.subject, args.known_at)
    else:
        ans = eng.current(args.subject)
    print(json.dumps({"value": ans.value, "status": ans.status,
                      "detail": ans.detail,
                      "provenance": list(ans.provenance)}, indent=2))
    return 0


def cmd_replay(args) -> int:
    log = freeze(fx.canonical_migration())
    ordered = temporal_sort(log.events(), log.by_id())
    projection = replay(ordered)
    print("projection_digest:", projection_digest(projection))
    print("log_digest:", log.digest())
    if args.out:
        log.write_jsonl(args.out)
        print("wrote", args.out)
    return 0


def cmd_health(_args) -> int:
    log = freeze(fx.canonical_migration())
    mat = MaterializedProjection()
    for e in log.events():
        mat.ingest(e, "2026-09-20T00:00:00Z")
    ordered = temporal_sort(log.events(), log.by_id())
    print(json.dumps(health_report(
        log, mat, projection_digest(replay(ordered))), indent=2))
    return 0


def cmd_benchmark(args) -> int:
    outdir = args.outdir
    from pathlib import Path
    import hashlib
    suite = run_suite(TemporalConfig(), live_transport=args.live)
    metrics = score_suite(suite)
    suite["metrics"] = metrics
    target = Path(outdir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "results.json").write_text(json.dumps(suite, indent=2))
    (target / "metrics.json").write_text(json.dumps(metrics, indent=2))
    log = freeze(fx.canonical_migration())
    log.write_jsonl(target / "events.jsonl")
    manifest = {
        "suite": suite["suite"],
        "frozen_at": suite["frozen_at"],
        "event_schema_version": "temporal-event-v0.1",
        "reducer_version": "temporal-reducer-v0.1",
        "fixture_version": "e8-fixture-v0.1",
        "transport_mode": "live-zeromq" if args.live else "emulated-disorder",
        "event_log_hash": log.digest(),
        "instrument_version": "benchmark-v0.1",
    }
    try:
        import zmq
        manifest["pyzmq_version"] = zmq.__version__
    except Exception:
        manifest["pyzmq_version"] = "unknown"
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (target / "config.json").write_text(
        json.dumps(suite["config"], indent=2))
    n_pass = sum(1 for m in ("temporal_role_accuracy",
                             "order_invariant_stability",
                             "late_arrival_robustness",
                             "future_effective_accuracy",
                             "correction_revision_accuracy",
                             "partial_order_calibration",
                             "sequence_gap_detection",
                             "projection_rebuild_equivalence")
                 if metrics.get(m) == 1.0)
    print(f"metrics: {n_pass}/8 core dimensions pass")
    print(f"frozen: {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="temporal_memory")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("demo", help="arrival vs semantic order demo")
    p.add_argument("--live", action="store_true",
                   help="use live ZeroMQ transport for capture")
    p.set_defaults(func=cmd_demo)
    p2 = sub.add_parser("permutations", help="order swap demo")
    p2.add_argument("scenario", nargs="?", default="postgres-migration")
    p2.set_defaults(func=cmd_permutations)
    p3 = sub.add_parser("trajectory", help="print a subject trajectory")
    p3.add_argument("subject", nargs="?")
    p3.set_defaults(func=cmd_trajectory)
    p4 = sub.add_parser("query", help="standpoint query")
    p4.add_argument("--subject", default=fx.SUBJECT_BACKEND)
    p4.add_argument("--condition", default="T3-temporal")
    p4.add_argument("--valid-at", default=None)
    p4.add_argument("--known-at", default=None)
    p4.set_defaults(func=cmd_query)
    p5 = sub.add_parser("replay", help="deterministic replay + digest")
    p5.add_argument("--out", default=None)
    p5.set_defaults(func=cmd_replay)
    p6 = sub.add_parser("health", help="structural health report")
    p6.set_defaults(func=cmd_health)
    p7 = sub.add_parser("benchmark", help="run E8 suite and freeze results")
    p7.add_argument("--outdir", required=True)
    p7.add_argument("--live", action="store_true")
    p7.set_defaults(func=cmd_benchmark)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
