"""Build the Chapter 6 task-by-capability matrix against the live systems.

Usage from the solution directory:

    python run_nexus_matrix.py --capabilities NONE,RAG,ASSOCIATIVE
    python run_nexus_matrix.py --capabilities GRAPH_DRIFT --tasks q1-locate-eventstore,q3-why-postgres

Every cell is cached, so this can be run in stages: the cheap
capabilities first, the expensive graph modes afterwards, DRIFT on a
named subset. Progress is printed unbuffered so a long background run
can be followed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent
INSTRUMENT_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark"
for _candidate in (str(SOLUTION_ROOT), str(INSTRUMENT_ROOT)):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from memory_nexus.config import NexusConfig  # noqa: E402
from memory_nexus.evaluation.runner import build_matrix  # noqa: E402
from memory_nexus.evaluation.utility import Utility  # noqa: E402
from memory_nexus.systems import bring_up, build_reader, load_tasks  # noqa: E402

RUNS_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark" / "runs"


def code_commit() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=str(SOLUTION_ROOT),
        )
        return proc.stdout.strip() or "unspecified"
    except Exception:
        return "unspecified"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capabilities", default=None)
    parser.add_argument("--tasks", default=None)
    parser.add_argument("--run-id", default="ch6-matrix")
    parser.add_argument("--reader", default=None)
    args = parser.parse_args(argv)

    overrides = {"code_commit": code_commit()}
    if args.reader:
        from memory_nexus.config import ReaderConfig

        overrides["reader"] = ReaderConfig(model=args.reader)
    config = NexusConfig.from_env(**overrides)

    print("bringing up systems...", flush=True)
    systems, registry, report = bring_up(config)
    print(report.render(), flush=True)

    tasks, payload, families = load_tasks()
    reader, _generator = build_reader(config)

    capabilities = (
        [c.strip() for c in args.capabilities.split(",") if c.strip()]
        if args.capabilities
        else registry.available_ids()
    )
    task_ids = (
        [t.strip() for t in args.tasks.split(",") if t.strip()]
        if args.tasks
        else None
    )
    total = len(task_ids or tasks) * len(capabilities)
    print(f"cells to cover: {total}", flush=True)

    counter = {"n": 0}
    started = time.perf_counter()

    def progress(task_id, capability_id, note):
        counter["n"] += 1
        elapsed = time.perf_counter() - started
        print(
            f"[{counter['n']:>3}/{total}] {elapsed:7.0f}s "
            f"{task_id:<26} {capability_id:<14} {note}",
            flush=True,
        )

    matrix = build_matrix(
        config=config,
        registry=registry,
        systems=systems,
        tasks=tasks,
        reader=reader,
        capabilities=capabilities,
        task_ids=task_ids,
        progress=progress,
    )

    run_dir = RUNS_ROOT / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    matrix.manifest["code_commit"] = config.code_commit
    matrix.manifest["bring_up"] = {
        "healthy": sorted(report.healthy),
        "degraded": report.degraded,
        "absent": report.absent,
        "details": report.details,
    }
    matrix.manifest["routing_families"] = families
    matrix.save(run_dir / "matrix.json")

    utility = Utility(config.utility)
    summary = {
        "fixed_policies": matrix.fixed_policy_scores(utility),
        "dominance": matrix.dominance(utility),
        "utility_weights": config.utility.to_dict(),
    }
    (run_dir / "matrix-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary["fixed_policies"], indent=2, sort_keys=True),
          flush=True)
    print(f"wrote {run_dir / 'matrix.json'}", flush=True)
    if systems.baseline is not None:
        systems.baseline.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
