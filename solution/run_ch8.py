"""Frozen Chapter 8 benchmark driver: runs the E8 suite and freezes artifacts.

Usage:
    python solution/run_ch8.py [--live] [--outdir experiments/benchmark/runs/ch8-...]
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

from temporal_memory import fixtures as fx  # noqa: E402
from temporal_memory.config import TemporalConfig  # noqa: E402
from temporal_memory.experiments import freeze, run_suite  # noqa: E402
from temporal_memory.metrics import score_suite  # noqa: E402


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--outdir", default=None)
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else (
        ROOT / "experiments" / "benchmark" / "runs" / f"ch8-{stamp}-temporal")
    outdir.mkdir(parents=True, exist_ok=True)

    config = TemporalConfig()
    suite = run_suite(config, live_transport=args.live)
    metrics = score_suite(suite)
    suite["metrics"] = metrics

    (outdir / "results.json").write_text(json.dumps(suite, indent=2))
    (outdir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    log = freeze(fx.canonical_migration())
    log.write_jsonl(outdir / "events.jsonl")
    (outdir / "arrival-log.jsonl").write_text(
        "".join(json.dumps({"event_id": r["envelope"]["event_id"],
                            "ingest_seq": r["ingest_seq"],
                            "received_at": r["received_at"],
                            "event_time": r["envelope"]["event_time"]}) + "\n"
                for r in log.records()))
    from temporal_memory.experiments import (exp_e8b_sensitive,
                                             exp_e8c_invariant)
    (outdir / "permutations.json").write_text(json.dumps(
        {"sensitive": exp_e8b_sensitive(), "invariant": exp_e8c_invariant()},
        indent=2))
    try:
        import zmq
        pyzmq_version = zmq.__version__
    except Exception:
        pyzmq_version = "unknown"
    manifest = {
        "suite": suite["suite"],
        "frozen_at": suite["frozen_at"],
        "code_commit": _commit(),
        "event_schema_version": "temporal-event-v0.1",
        "reducer_version": "temporal-reducer-v0.1",
        "fixture_version": config.fixture_version,
        "projection_version": config.projection_version,
        "transport_mode": "live-zeromq" if args.live else "emulated-disorder",
        "pyzmq_version": pyzmq_version,
        "event_log_hash": log.digest(),
        "instrument_version": "benchmark-v0.1",
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (outdir / "config.json").write_text(json.dumps(config.to_dict(), indent=2))
    print(json.dumps(metrics, indent=2))
    print(f"frozen: {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
