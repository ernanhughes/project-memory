"""Frozen Chapter 10 benchmark driver: runs the E10 suite and freezes artifacts.

Usage:
    python solution/run_ch10.py [--outdir experiments/benchmark/runs/ch10-...]
                               [--budget 1500] [--no-reader] [--no-embeddings]

Every run freezes the manifest (corpus digest, frames, policy version,
retriever, reader, budgets, code commit), the suite results and metrics,
the project and work frames, every ContextBundle, and every ContextTrace.
The traces are the point: an answer alone cannot say where a failure
happened.
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

from context_frames import fixtures as fx  # noqa: E402
from context_frames.corpus import corpus, corpus_digest  # noqa: E402
from context_frames.experiments import Harness, run_suite  # noqa: E402
from context_frames.model import PROJECT_FRAME_SCHEMA, WORK_FRAME_SCHEMA  # noqa: E402
from context_frames.policy import (CANDIDATE_POOL, DEFAULT_BUDGET_TOKENS,  # noqa: E402
                                   LADDER, POLICY_VERSION)
from context_frames.reader import Reader  # noqa: E402


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            text=True).strip()
    except Exception:
        return "unknown"


def _write_jsonl(path: Path, rows) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET_TOKENS)
    parser.add_argument("--no-reader", action="store_true")
    parser.add_argument("--no-embeddings", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else (
        ROOT / "experiments" / "benchmark" / "runs"
        / f"ch10-{stamp}-context-frames")
    outdir.mkdir(parents=True, exist_ok=True)

    reader = None if args.no_reader else Reader()
    if reader is not None and not reader.available():
        print("reader service unreachable; continuing without answers")
        reader = None

    suite = run_suite(budget=args.budget, reader=reader,
                      use_embeddings=not args.no_embeddings)
    (outdir / "results.json").write_text(json.dumps(suite, indent=2))
    (outdir / "metrics.json").write_text(json.dumps({
        "ladder_mean": suite["experiments"]["E10-A"]["mean_over_tasks"],
        "goal_divergence": {
            "baseline_jaccard": suite["experiments"]["E10-B"]["baseline_jaccard"],
            "full_jaccard": suite["experiments"]["E10-B"]["full_jaccard"]},
        "cross_project_leakage": suite["experiments"]["E10-C"]["mean_leakage"],
        "frame_builder": suite["experiments"]["E10-K"]["summary"],
        "answers": suite["experiments"]["E10-L"].get("summary"),
        "policy_backtest": {
            "promoted": suite["experiments"]["E10-N"]["promoted"],
            "rejected": suite["experiments"]["E10-N"]["rejected"]},
    }, indent=2))

    # Corpus, frames and tasks: the inputs, frozen alongside the outputs.
    _write_jsonl(outdir / "corpus.jsonl", [u.to_dict() for u in corpus()])
    (outdir / "project-frames.json").write_text(json.dumps(
        {pid: builder().to_dict() for pid, builder
         in fx.PROJECT_FRAMES.items()}, indent=2))
    _write_jsonl(outdir / "tasks.jsonl",
                 [t.to_dict() for t in fx.all_tasks()])

    # Every bundle and every trace, for every condition on the ladder.
    harness = Harness(budget=args.budget, reader=reader,
                      use_embeddings=not args.no_embeddings)
    bundles = outdir / "bundles"
    traces = outdir / "traces"
    bundles.mkdir(exist_ok=True)
    traces.mkdir(exist_ok=True)
    digests = []
    for task in fx.all_tasks():
        for condition in [c.name for c in LADDER] + ["CO"]:
            bundle, trace = harness.build(condition, task)
            name = f"{task.task_id}-{condition}"
            (bundles / f"{name}.json").write_text(
                json.dumps(bundle.to_dict(), indent=2))
            (traces / f"{name}.json").write_text(
                json.dumps(trace.to_dict(), indent=2))
            digests.append({"task": task.task_id, "condition": condition,
                            "bundle_digest": bundle.digest(),
                            "bundle_tokens": bundle.tokens})
    _write_jsonl(outdir / "bundle-digests.jsonl", digests)

    manifest = {
        "suite": suite["suite"],
        "run_id": outdir.name,
        "created_at": stamp,
        "corpus_digest": corpus_digest(),
        "corpus_units": suite["corpus_units"],
        "task_count": len(fx.all_tasks()),
        "policy_version": POLICY_VERSION,
        "project_frame_schema": PROJECT_FRAME_SCHEMA,
        "work_frame_schema": WORK_FRAME_SCHEMA,
        "retriever": suite["retriever"],
        "candidate_pool": CANDIDATE_POOL,
        "budget_tokens": args.budget,
        "conditions": [{"name": c.name, "label": c.label} for c in LADDER]
                      + [{"name": "CO", "label": "ledger oracle ceiling"}],
        "reader": reader.name if reader is not None else None,
        "reader_prompt_sha": None if reader is None else __import__(
            "hashlib").sha256(
            __import__("context_frames.reader", fromlist=["SYSTEM_PROMPT"])
            .SYSTEM_PROMPT.encode()).hexdigest()[:16],
        "code_commit": _commit(),
        "ledger_audit": suite["ledger_audit"],
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    ladder = suite["experiments"]["E10-A"]["mean_over_tasks"]
    print(f"wrote {outdir}")
    for name, row in ladder.items():
        print(f"  {name} {row['label']:<32} "
              f"must={row['must_include_recall']:.3f} "
              f"prec={row['context_precision']:.3f} "
              f"harm={row['harmful_admission']:.3f} "
              f"leak={row['cross_project_leakage']:.3f} "
              f"tok={row['bundle_tokens']:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
