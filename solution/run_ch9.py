"""Frozen Chapter 9 benchmark driver: runs the E9 suite and freezes artifacts.

Usage:
    python solution/run_ch9.py [--outdir experiments/benchmark/runs/ch9-...]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "solution"))

from open_loops import fixtures as fx  # noqa: E402
from open_loops.config import OpenLoopConfig  # noqa: E402
from open_loops.experiments import freeze, run_suite  # noqa: E402
from open_loops.metrics import score_suite  # noqa: E402
from open_loops.status import resolve_status  # noqa: E402


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=None)
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else (
        ROOT / "experiments" / "benchmark" / "runs" / f"ch9-{stamp}-open-loops")
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
    expectations = [fx.EXP_BACKUP(), fx.EXP_DOCS(), fx.EXP_FIXTURES(),
                    fx.EXP_TUNE(), fx.EXP_STAGING()]
    (outdir / "expectations.jsonl").write_text("".join(
        json.dumps(e.to_dict(), sort_keys=True) + "\n" for e in expectations))
    (outdir / "arrival-log.jsonl").write_text("".join(
        json.dumps({"event_id": r["envelope"]["event_id"],
                    "ingest_seq": r["ingest_seq"]}) + "\n"
        for r in log.records()))
    (outdir / "search-footprints.jsonl").write_text("".join(
        json.dumps(resolve_status(
            e, log, "2024-08-31T00:00:00Z",
            texts=texts).footprint.to_dict()) + "\n"
        for e in expectations))
    traces = outdir / "traces"
    traces.mkdir(exist_ok=True)
    for exp in expectations:
        lines = []
        for cut in ("2024-07-20T00:00:00Z", "2024-08-25T00:00:00Z",
                    "2024-08-31T00:00:00Z"):
            report = resolve_status(exp, log, cut, texts=texts)
            lines.append({"valid_at": cut, **report.to_dict()})
        (traces / f"{exp.expectation_id}.json").write_text(
            json.dumps(lines, indent=2))
    from temporal_memory.model import SCHEMA_VERSION
    manifest = {
        "suite": suite["suite"],
        "frozen_at": suite["frozen_at"],
        "code_commit": _commit(),
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


if __name__ == "__main__":
    raise SystemExit(main())
