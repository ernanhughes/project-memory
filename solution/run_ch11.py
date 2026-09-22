"""Frozen Chapter 11 benchmark driver: runs the E-11 suite and freezes artifacts.

Usage:
    python solution/run_ch11.py [--outdir experiments/benchmark/runs/ch11-...]

Freezes the manifest (fixture version, gate version, standpoint, code
commit), per-task results for every condition, every candidate with its
full triple and gate decision, metrics, and the backtest outcome.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "solution"))

from derived_loops import fixtures as fx  # noqa: E402
from derived_loops.baselines import CONDITIONS, run_condition  # noqa: E402
from derived_loops.experiments import run_suite  # noqa: E402
from derived_loops.metrics import score_task  # noqa: E402
from derived_loops.model import GATE_VERSION  # noqa: E402


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
        ROOT / "experiments" / "benchmark" / "runs"
        / f"ch11-{stamp}-derived-loops")
    outdir.mkdir(parents=True, exist_ok=True)

    suite = run_suite()
    (outdir / "results.json").write_text(json.dumps(suite, indent=2))

    metrics = {c: suite["conditions"][c]["aggregate"]
               for c in CONDITIONS}
    metrics["backtest"] = suite["backtest"]
    (outdir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    tasks = fx.all_tasks()
    (outdir / "tasks.json").write_text(json.dumps(
        [t.to_dict() for t in tasks], indent=2))

    cond_dir = outdir / "conditions"
    cond_dir.mkdir(exist_ok=True)
    for condition in CONDITIONS:
        rows = []
        for task in tasks:
            decisions = run_condition(condition, task)
            score = score_task(task, decisions)
            rows.append({
                "task_id": task.task_id,
                "decisions": [d.to_dict() for d in decisions],
                "score": score})
        (cond_dir / f"{condition}.json").write_text(
            json.dumps(rows, indent=2))

    corpus_text = json.dumps([t.to_dict() for t in tasks], sort_keys=True)
    manifest = {
        "suite": suite["suite"],
        "run_id": outdir.name,
        "created_at": stamp,
        "fixture_version": "corpus_import-v1",
        "gate_version": GATE_VERSION,
        "standpoint": tasks[0].standpoint,
        "conditions": list(CONDITIONS),
        "task_count": len(tasks),
        "corpus_digest": hashlib.sha256(
            corpus_text.encode()).hexdigest()[:16],
        "code_commit": _commit(),
        "reader": None,
        "note": "fixture-level deterministic run; zero model calls",
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    def _fmt(v) -> str:
        return f"{v:.4f}" if v is not None else "null"
    print(f"wrote {outdir}")
    for condition in CONDITIONS:
        agg = metrics[condition]
        print(f"  {condition:<14} "
              f"prec={_fmt(agg['mean_inferred_precision'])} "
              f"rec={_fmt(agg['mean_inferred_recall'])} "
              f"micro={_fmt(agg['micro_precision'])}/"
              f"{_fmt(agg['micro_recall'])} "
              f"harm_tasks={agg['tasks_with_harmful']} "
              f"abst={_fmt(agg['abstention_rate'])}")
    b = suite["backtest"]
    print(f"  backtest {b['candidate']}: gain={b['primary_gain']} "
          f"promoted={b['promoted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
