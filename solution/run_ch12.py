"""Frozen Chapter 12 behaviour driver.

Runs the behavioural suite (controlled fixtures + anomaly probes +
real-project transfer) through a fixed reader, freezes manifest,
metrics, contexts, outputs, structured actions, paired comparisons,
ablations, failure attribution, and the real-transfer set.
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

from behavior_eval import contexts as C  # noqa: E402
from behavior_eval import real_transfer as RT  # noqa: E402
from behavior_eval.experiments import PLAN, run_suite, summarize  # noqa: E402
from behavior_eval.model import (  # noqa: E402
    BEHAVIOR_SCHEMA_VERSION,
    FIXTURE_VERSION,
    GRADER_VERSION,
)
from behavior_eval.prompts import PROMPT_VERSION  # noqa: E402
from behavior_eval.runner import ReaderClient  # noqa: E402
from context_frames.reader import Reader  # noqa: E402


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            text=True).strip()
    except Exception:
        return "unknown"


def _live_reader(model: str):
    import time
    import urllib.error
    from behavior_eval.runner import capped_ask
    from context_frames.reader import SYSTEM_PROMPT
    reader = Reader(model=model)
    if not reader.available():
        return None
    def ask(prompt: str) -> str:
        last: Exception | None = None
        for attempt in range(4):
            try:
                return capped_ask(model, reader.host, SYSTEM_PROMPT,
                                  prompt)
            except (TimeoutError, urllib.error.URLError,
                    ConnectionError, OSError) as exc:
                last = exc
                time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"reader unreachable after retries: {last}")
    return ask


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--no-repeats", action="store_true")
    parser.add_argument("--tasks", default=None,
                        help="comma-separated task subset")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else (
        ROOT / "experiments" / "benchmark" / "runs"
        / f"ch12-{stamp}-behavior")
    outdir.mkdir(parents=True, exist_ok=True)
    cache_dir = outdir / "reader-cache"
    cache_dir.mkdir(exist_ok=True)

    live = _live_reader(args.model)
    if live is None:
        print("no live reader reachable; aborting (no services in unit "
              "tests, but the frozen run needs the reader)")
        return 2
    client = ReaderClient(args.model, cache_dir, live=live)

    from behavior_eval.tasks import all_tasks
    tasks = all_tasks()
    if args.tasks:
        want = set(args.tasks.split(","))
        tasks = [t for t in tasks if t.task_id in want]

    resume = None
    prior = outdir / "conditions.json"
    if prior.exists():
        resume = json.loads(prior.read_text())
        print(f"resuming: {sum(len(v) for v in resume.values())} "
              f"stored rows reused when context hashes match")

    suite = run_suite(client, tasks, repeats=not args.no_repeats,
                      resume=resume)
    summary = summarize(suite)

    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    serial = {}
    for cond, rows in suite["conditions"].items():
        serial[cond] = []
        for row in rows:
            outcome = dict(row["outcome"])
            serial[cond].append({"outcome": outcome,
                                 "note": row["note"]})
    (outdir / "conditions.json").write_text(json.dumps(serial, indent=2))
    contexts_out = {}
    for cond, rows in suite["conditions"].items():
        for row in rows:
            o = row["outcome"]
            contexts_out[f"{o['task_id']}|{cond}|{o['repeat_index']}"] = {
                "context": row.get("context", ""),
                "context_hash": o["context_hash"],
                "tokens": o["context_tokens"],
                "note": row["note"]}
    (outdir / "contexts.json").write_text(json.dumps(contexts_out,
                                                     indent=2))
    (outdir / "ablation_base.json").write_text(
        json.dumps(suite["ablation_base"], indent=2))
    manifest = {
        "suite": "E-12-behavior",
        "run_id": outdir.name,
        "created_at": stamp,
        "behavior_schema_version": BEHAVIOR_SCHEMA_VERSION,
        "grader_version": GRADER_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "benchmark_contract": ("benchmark-v0.1 plus diagnostic "
                               "behavioural dimensions (no contract change; "
                               "see spec/ch9-14-issues.md item 5 note)"),
        "reader": client.name,
        "decoding": ("temperature 0, seed 7, num_predict 1024 "
                     "(Ch12-bounded; shared frozen reader untouched)"),
        "ch10_source_run": "ch10-20260920T163314Z-context-frames",
        "ch11_source_run": "ch11-20260920T171039Z-derived-loops",
        "ch14_source_run": "ch14-20260920T174259Z-context-assembly",
        "token_estimator": "chars//4 (estimated tokens)",
        "code_commit": _commit(),
        "reader_cache_calls": client.calls,
        "reader_cache_hits": client.hits,
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"wrote {outdir}  calls={client.calls} hits={client.hits}")
    for cond, stats in summary["mean_by_condition"].items():
        print(f"  {cond}: success={stats['task_success']} "
              f"harmful={stats['harmful']} n={stats['n']}")
    print("influence:", summary["influence"]["counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
