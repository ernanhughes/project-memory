"""Muse compact-context transfer driver (SR-3) for Chapter 14.

No budget sweep, no reassembly. Frozen rendered contexts only, key
conditions: A0 raw selected, A6 @ 768, A6 full, CO-auditable. Muse
answers each task query over the frozen render; answers are scored
with the existing deterministic key-claim scorer
(``context_frames.metrics.score_answer``).

Question: does a stronger reader need the same amount and shape of
context? The budget is held fixed; the reader is the variable.

Output: ``experiments/benchmark/runs/sr3-ch14-<stamp>-muse``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "solution"))

from context_frames import fixtures as fx  # noqa: E402
from context_frames import metrics as M  # noqa: E402
from context_frames.reader import Reader  # noqa: E402
from providers.opencode import (  # noqa: E402
    OpenCodeModel,
    resolve_api_key,
    resolve_model,
    resolve_reasoning_effort,
)

SOURCE_RUN = "ch14-20260920T174259Z-context-assembly"
SOURCE_DIR = (ROOT / "experiments" / "benchmark" / "runs" / SOURCE_RUN
              / "rendered-contexts")
CONDITIONS = (("A0-raw", "full"), ("A6-composed", "768"),
              ("A6-composed", "full"), ("CO-auditable", "full"))


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chapter 14 compact-context transfer with Muse Spark.")
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="first-attempt output budget; retry once at 2x "
                             "on empty output (full renders need headroom "
                             "for reasoning)")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    model = resolve_model(args.model)
    effort = resolve_reasoning_effort(args.reasoning_effort)
    tasks = fx.all_tasks()
    if args.dry_run:
        print(f"dry-run: model={model} reasoning_effort={effort} "
              f"tasks={len(tasks)} calls={len(tasks) * len(CONDITIONS)} "
              f"key_configured={bool(resolve_api_key())}")
        return 0
    if not resolve_api_key():
        print("no Muse credentials (no live calls made)")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else (
        ROOT / "experiments" / "benchmark" / "runs"
        / f"sr3-ch14-{stamp}-muse")
    outdir.mkdir(parents=True, exist_ok=True)
    run_session = f"memory-{outdir.name}"
    backend = OpenCodeModel()
    totals: dict = {}
    records: list[dict] = []
    rows: dict = {}
    # Resume: reuse frozen rows/records when the rendered context is
    # unchanged (no re-query, no repay).
    probe_path = outdir / "reader-probe-muse.json"
    calls_path = outdir / "muse_calls.jsonl"
    if probe_path.exists():
        rows = json.loads(probe_path.read_text())
    if calls_path.exists():
        records = [json.loads(line)
                   for line in calls_path.read_text().splitlines()
                   if line.strip()]
        for rec in records:
            usage = rec.get("usage") or {}
            for k in ("input_tokens", "cached_input_tokens",
                      "output_tokens", "reasoning_tokens", "total_tokens"):
                totals[k] = totals.get(k, 0) + int(usage.get(k, 0) or 0)
            totals["calls"] = totals.get("calls", 0) + 1

    for cond, budget in CONDITIONS:
        rendered = json.loads(
            (SOURCE_DIR / f"{cond}-budget-{budget}.json").read_text())
        for task in tasks:
            context = rendered[task.task_id]
            key = f"{task.task_id}|{cond}|{budget}"
            if key in rows:
                print(f"{key}: resumed "
                      f"coverage={rows[key]['key_claim_coverage']}")
                continue
            prompt = Reader.build_prompt(
                task.work_frame.objective, task.query, context)
            result = backend.generate(
                prompt, model=model, temperature=args.temperature,
                max_tokens=args.max_tokens, reasoning_effort=effort,
                session_id=run_session)
            if result.get("error"):
                raise RuntimeError(
                    f"muse reader failed [{result.get('error_type')}] "
                    f"on {task.task_id}/{cond}/{budget}: "
                    f"{result.get('error')}")
            answer = result["response"]
            scored = M.score_answer(task, answer)
            usage = result.get("usage") or {}
            for k in ("input_tokens", "cached_input_tokens",
                      "output_tokens", "reasoning_tokens", "total_tokens"):
                totals[k] = totals.get(k, 0) + int(usage.get(k, 0) or 0)
            totals["calls"] = totals.get("calls", 0) + 1
            rows[f"{task.task_id}|{cond}|{budget}"] = {
                "key_claim_coverage": scored.get("key_claim_coverage"),
                "forbidden_claim_rate": scored.get("forbidden_claim_rate"),
                "counted_tokens": len(context) // 4,
            }
            records.append({
                "task": task.task_id, "condition": cond, "budget": budget,
                "model": model, "attempts": result.get("attempts"),
                "usage": usage, "answer": answer,
                "key_claim_coverage": scored.get("key_claim_coverage"),
            })
            # Incremental freeze so a failed call never loses done rows.
            (outdir / "reader-probe-muse.json").write_text(
                json.dumps(rows, indent=2))
            (outdir / "muse_calls.jsonl").write_text(
                "".join(json.dumps(r, sort_keys=True) + "\n"
                        for r in records))
            print(f"{task.task_id}|{cond}|{budget}: "
                  f"coverage={scored.get('key_claim_coverage')} "
                  f"forbidden={scored.get('forbidden_claim_rate')}")

    (outdir / "reader-probe-muse.json").write_text(
        json.dumps(rows, indent=2))
    (outdir / "muse_calls.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
    host = urlparse(OpenCodeModel().base_url).netloc or "opencode.ai"
    manifest = {
        "suite": "SR-3 compact-context transfer",
        "source": SOURCE_RUN,
        "run_id": outdir.name,
        "created_at": stamp,
        "conditions": [f"{c}@{b}" for c, b in CONDITIONS],
        "reader": f"opencode:{model}@t0",
        "reader_provider": "opencode-zen-go",
        "reader_model": model,
        "reader_backend": f"opencode-responses ({host})",
        "reasoning_effort": effort,
        "temperature": args.temperature,
        "max_output_tokens": args.max_tokens,
        "session_id": run_session,
        "scorer": "context_frames.metrics.score_answer (unchanged)",
        "code_commit": _commit(),
        "muse_usage_totals": totals,
        "cost": "not computed",
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {outdir} totals={totals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
