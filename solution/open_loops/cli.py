"""CLI for open loops: demo, list, status, history, explain, verify,
reverify, benchmark, health. All commands run on real fixture data.
"""

from __future__ import annotations

import argparse
import json
import sys

from temporal_memory.log import EventLog

from . import fixtures as fx
from .config import OpenLoopConfig
from .experiments import freeze, run_suite
from .health import health_report
from .materialized import MaterializedOpenList
from .metrics import score_suite
from .reverify import reverify, run_reverification
from .status import resolve_status


def _canonical():
    events, texts = fx.canonical_history()
    log = freeze(events)
    expectations = [fx.EXP_BACKUP(), fx.EXP_DOCS(), fx.EXP_FIXTURES(),
                    fx.EXP_TUNE(), fx.EXP_STAGING()]
    return log, texts, expectations


def cmd_demo(_args) -> int:
    log, texts, expectations = _canonical()
    print("Migration complete; consequences checked per expectation:\n")
    for exp in expectations:
        report = resolve_status(exp, log, "2024-08-31T00:00:00Z", texts=texts)
        close = (report.closing_evidence[0] if report.closing_evidence
                 else "none found")
        print(f"{exp.expectation_id:12} {exp.statement}")
        print(f"  opened: {', '.join(exp.opening_evidence)}")
        print(f"  status: {report.status} [{report.closure_tier or 'no close'}]")
        print(f"  closing evidence: {close}")
        if report.deadline_passed:
            print("  deadline: passed while OPEN")
        print()
    return 0


def cmd_list(args) -> int:
    log, texts, expectations = _canonical()
    ml = MaterializedOpenList()
    for exp in expectations:
        ml.register(exp)
    for eid, text in texts.items():
        ml.note_text(eid, text)
    ml.refresh_all(log, args.valid_at)
    scope = None if args.scope == "all" else args.scope
    for report in ml.list_open(scope):
        print(f"{report.expectation_id}: OPEN "
              f"({report.confidence_class}) opened by "
              f"{','.join(report.opening_evidence)}")
    return 0


def cmd_status(args) -> int:
    log, texts, expectations = _canonical()
    by_id = {e.expectation_id: e for e in expectations}
    exp = by_id.get(args.expectation_id)
    if exp is None:
        print(f"unknown expectation: {args.expectation_id}")
        return 1
    report = resolve_status(exp, log, args.valid_at,
                            known_at=args.known_at, texts=texts)
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def cmd_history(args) -> int:
    log, texts, expectations = _canonical()
    by_id = {e.expectation_id: e for e in expectations}
    exp = by_id.get(args.expectation_id)
    if exp is None:
        print(f"unknown expectation: {args.expectation_id}")
        return 1
    for cut in ("2024-07-20T00:00:00Z", "2024-08-25T00:00:00Z",
                "2024-08-31T00:00:00Z"):
        report = resolve_status(exp, log, cut, texts=texts)
        print(f"{cut[:10]}: {report.status} "
              f"[{report.closure_tier or report.confidence_class}]")
    return 0


def cmd_explain(args) -> int:
    log, texts, expectations = _canonical()
    by_id = {e.expectation_id: e for e in expectations}
    exp = by_id.get(args.expectation_id)
    if exp is None:
        print(f"unknown expectation: {args.expectation_id}")
        return 1
    report = resolve_status(exp, log, args.valid_at, texts=texts)
    print(f"{exp.expectation_id}: {exp.statement}")
    print(f"status: {report.status} — {report.detail}")
    print(f"opening evidence: {', '.join(report.opening_evidence)}")
    print(f"closing evidence: {', '.join(report.closing_evidence) or 'none found'}")
    if report.footprint is not None:
        fp = report.footprint
        print(f"searched: {', '.join(fp.searched_sources)} "
              f"through {fp.searched_until}")
        print(f"candidates examined: {fp.candidate_closures_examined}; "
              f"gaps: {', '.join(fp.gaps) or 'none'}")
    print("An item is open because opening evidence exists and no valid "
          "closing transition was observed — not because nothing was found.")
    return 0


def cmd_verify(args) -> int:
    log, texts, expectations = _canonical()
    by_id = {e.expectation_id: e for e in expectations}
    exp = by_id.get(args.expectation_id)
    if exp is None:
        print(f"unknown expectation: {args.expectation_id}")
        return 1
    report = reverify(exp, log, args.valid_at, texts=texts)
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def cmd_reverify(args) -> int:
    log, texts, expectations = _canonical()
    ml = MaterializedOpenList()
    for exp in expectations:
        ml.register(exp)
    for eid, text in texts.items():
        ml.note_text(eid, text)
    ml.refresh_all(log, "2024-08-25T00:00:00Z")
    result = run_reverification(ml, log, args.valid_at)
    print(json.dumps(result, indent=2))
    return 0


def cmd_benchmark(args) -> int:
    from pathlib import Path
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    config = OpenLoopConfig()
    suite = run_suite(config)
    metrics = score_suite(suite)
    suite["metrics"] = metrics
    (outdir / "results.json").write_text(json.dumps(suite, indent=2))
    (outdir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    events, texts = fx.canonical_history()
    log = freeze(events)
    log.write_jsonl(outdir / "events.jsonl")
    (outdir / "expectations.jsonl").write_text("".join(
        json.dumps(e.to_dict(), sort_keys=True) + "\n"
        for e in [fx.EXP_BACKUP(), fx.EXP_DOCS(), fx.EXP_FIXTURES(),
                  fx.EXP_TUNE(), fx.EXP_STAGING()]))
    (outdir / "arrival-log.jsonl").write_text("".join(
        json.dumps({"event_id": r["envelope"]["event_id"],
                    "ingest_seq": r["ingest_seq"]}) + "\n"
        for r in log.records()))
    (outdir / "search-footprints.jsonl").write_text("".join(
        json.dumps(resolve_status(
            e, log, "2024-08-31T00:00:00Z",
            texts=texts).footprint.to_dict()) + "\n"
        for e in [fx.EXP_BACKUP(), fx.EXP_DOCS(), fx.EXP_FIXTURES(),
                  fx.EXP_TUNE(), fx.EXP_STAGING()]))
    try:
        from temporal_memory.model import SCHEMA_VERSION
    except Exception:  # noqa: BLE001
        SCHEMA_VERSION = "unknown"
    manifest = {
        "suite": suite["suite"],
        "frozen_at": suite["frozen_at"],
        "event_schema_version": SCHEMA_VERSION,
        "expectation_schema_version": config.expectation_schema_version,
        "resolver_version": config.resolver_version,
        "fixture_version": config.fixture_version,
        "temporal_memory": "temporal-event-v0.1 / temporal-reducer-v0.1",
        "instrument_version": "benchmark-v0.1",
        "event_log_hash": log.digest(),
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (outdir / "config.json").write_text(json.dumps(config.to_dict(), indent=2))
    print(json.dumps(metrics, indent=2))
    print(f"frozen: {outdir}")
    return 0


def cmd_health(_args) -> int:
    log, texts, expectations = _canonical()
    ml = MaterializedOpenList()
    for exp in expectations:
        ml.register(exp)
    ml.refresh_all(log, "2024-08-31T00:00:00Z")
    print(json.dumps(health_report(expectations, log, ml), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="open_loops")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, extra in (
            ("demo", cmd_demo, None),
            ("list", cmd_list, "scope"),
            ("status", cmd_status, "exp"),
            ("history", cmd_history, "exp"),
            ("explain", cmd_explain, "exp"),
            ("verify", cmd_verify, "exp"),
            ("reverify", cmd_reverify, None),
            ("benchmark", cmd_benchmark, "outdir"),
            ("health", cmd_health, None)):
        p = sub.add_parser(name)
        if extra == "scope":
            p.add_argument("--scope", default="all")
            p.add_argument("--valid-at", default="2024-08-31T00:00:00Z")
        elif extra == "exp":
            p.add_argument("expectation_id")
            p.add_argument("--valid-at", default="2024-08-31T00:00:00Z")
            p.add_argument("--known-at", default=None)
        elif extra == "outdir":
            p.add_argument("--outdir", required=True)
        elif name == "reverify":
            p.add_argument("--valid-at", default="2024-08-31T00:00:00Z")
        p.set_defaults(func=func)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
