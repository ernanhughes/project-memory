"""Muse frame-inference transfer driver (SR-2) for Chapter 10 E10-K.

Holds fixed: WorkSignals, frame schema, candidate memories,
ContextPolicy, retrieval (bm25+ollama:bge-m3+rrf60), corpus, ledger,
budget, and the existing WorkFrame prompt/parser/fallback in
``context_frames.frames``. The only variable is the inference
model behind ``infer_work_frame``'s ``reader.ask`` interface.

Muse emits the same WorkFrame representation through the same
parser, same allowed work types, same keyword fallback. No final
task answering: this tests Muse -> WorkFrame -> ContextPolicy ->
context-selection metrics only.

Output: ``experiments/benchmark/runs/sr2-ch10-<stamp>-muse``.
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
from context_frames.corpus import corpus_digest  # noqa: E402
from context_frames.experiments import Harness  # noqa: E402
from context_frames.frames import (  # noqa: E402
    infer_work_frame,
    keyword_work_frame,
)
from context_frames.model import (  # noqa: E402
    PROJECT_FRAME_SCHEMA,
    WORK_FRAME_SCHEMA,
)
from context_frames.policy import (  # noqa: E402
    DEFAULT_BUDGET_TOKENS,
    POLICY_VERSION,
)
from providers.opencode import (  # noqa: E402
    OpenCodeModel,
    resolve_api_key,
    resolve_model,
    resolve_reasoning_effort,
)

SOURCE_RUN = "ch10-20260920T163314Z-context-frames"


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            text=True).strip()
    except Exception:
        return "unknown"


class MuseFrameReader:
    """Minimal reader interface for frame inference (ask-only)."""

    def __init__(self, model: str, temperature: float, max_tokens: int,
                 reasoning_effort: str, session_id: str) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.session_id = session_id
        self.backend = OpenCodeModel()
        self.records: list[dict] = []
        self.totals: dict = {}

    @property
    def name(self) -> str:
        return f"opencode:{self.model}@t0"

    def available(self) -> bool:
        return bool(resolve_api_key(self.backend.api_key))

    def ask(self, prompt: str, session_id: str | None = None) -> str:
        result = self.backend.generate(
            prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort,
            session_id=session_id or self.session_id,
        )
        if result.get("error"):
            raise RuntimeError(
                f"muse frame inference failed [{result.get('error_type')}]: "
                f"{result.get('error')}")
        usage = result.get("usage") or {}
        for k in ("input_tokens", "cached_input_tokens", "output_tokens",
                  "reasoning_tokens", "total_tokens"):
            self.totals[k] = self.totals.get(k, 0) + int(usage.get(k, 0) or 0)
        self.totals["calls"] = self.totals.get("calls", 0) + 1
        request = dict(result.get("request") or {})
        self.records.append({
            "model": request.get("model"),
            "reasoning_effort": request.get("reasoning_effort"),
            "attempts": result.get("attempts"),
            "usage": usage,
            "response": result["response"],
            "session_id": session_id or self.session_id,
        })
        return result["response"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chapter 10 frame-inference transfer with Muse Spark.")
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET_TOKENS)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--no-embeddings", action="store_true",
                        help="lexical-only pool (deviation; record it)")
    parser.add_argument("--repeats", type=int, default=1,
                        help="independent inference repeats per task "
                             "(Test 5 replication; unique session per call)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    model = resolve_model(args.model)
    effort = resolve_reasoning_effort(args.reasoning_effort)
    if args.dry_run:
        print(f"dry-run: model={model} reasoning_effort={effort} "
              f"tasks={len(fx.all_tasks())} key_configured="
              f"{bool(resolve_api_key())}")
        return 0
    if not resolve_api_key():
        print("no Muse credentials (no live calls made)")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else (
        ROOT / "experiments" / "benchmark" / "runs"
        / f"sr2-ch10-{stamp}-muse")
    outdir.mkdir(parents=True, exist_ok=True)
    run_session = f"memory-{outdir.name}"
    reader = MuseFrameReader(model, args.temperature, args.max_tokens,
                             effort, run_session)
    harness = Harness(budget=args.budget, reader=None,
                      use_embeddings=not args.no_embeddings)

    rows = {}
    for task in fx.all_tasks():
        frame = fx.PROJECT_FRAMES[task.project_id]()
        declared = task.work_frame
        keyword = keyword_work_frame(
            declared.work_frame_id + "-kw", frame, declared.signals,
            declared.as_of, declared.objective)
        kw_scored, _, _ = harness.score("C6", task, work=keyword,
                                        suffix="-kw")
        declared_scored, _, _ = harness.score("C6", task)
        entry = {
            "declared_work_type": declared.work_type,
            "keyword_work_type": keyword.work_type,
            "keyword_correct": keyword.work_type == declared.work_type,
            "keyword_must_recall": kw_scored["must_include_recall"],
            "keyword_precision": kw_scored.get("context_precision"),
            "keyword_harm": kw_scored.get("harmful_admission"),
            "keyword_leak": kw_scored.get("cross_project_leakage"),
            "keyword_tokens": kw_scored.get("bundle_tokens"),
            "declared_must_recall": declared_scored["must_include_recall"],
        }
        inferred = infer_work_frame(
            declared.work_frame_id + "-muse", frame, declared.signals,
            declared.as_of, reader)
        inf_scored, _, _ = harness.score("C6", task, work=inferred,
                                         suffix="-muse")
        entry["muse_work_type"] = inferred.work_type
        entry["muse_objective"] = inferred.objective
        entry["muse_correct"] = inferred.work_type == declared.work_type
        entry["muse_derivation"] = inferred.derivation
        entry["muse_must_recall"] = inf_scored["must_include_recall"]
        entry["muse_precision"] = inf_scored.get("context_precision")
        entry["muse_harm"] = inf_scored.get("harmful_admission")
        entry["muse_leak"] = inf_scored.get("cross_project_leakage")
        entry["muse_tokens"] = inf_scored.get("bundle_tokens")
        entry["muse_provenance_complete"] = (
            inferred.unprovenanced_fields() == ())
        entry["muse_session"] = reader.session_id
        if args.repeats > 1:
            # Replication repeats: same input, independent sessions.
            reps = [{"repeat": 0, "work_type": inferred.work_type,
                     "objective": inferred.objective,
                     "correct": entry["muse_correct"],
                     "must_recall": entry["muse_must_recall"],
                     "harm": entry["muse_harm"],
                     "leak": entry["muse_leak"],
                     "session": reader.session_id}]
            for rep in range(1, args.repeats):
                reader.session_id = (
                    f"memory-{outdir.name}-{task.task_id}-r{rep}")
                inf_r = infer_work_frame(
                    f"{declared.work_frame_id}-muse-r{rep}", frame,
                    declared.signals, declared.as_of, reader)
                sc_r, _, _ = harness.score(
                    "C6", task, work=inf_r, suffix=f"-muse-r{rep}")
                reps.append(
                    {"repeat": rep, "work_type": inf_r.work_type,
                     "objective": inf_r.objective,
                     "correct": inf_r.work_type == declared.work_type,
                     "must_recall": sc_r["must_include_recall"],
                     "harm": sc_r.get("harmful_admission"),
                     "leak": sc_r.get("cross_project_leakage"),
                     "session": reader.session_id})
            from collections import Counter
            majority = Counter(r["work_type"] for r in reps).most_common(1)
            entry["muse_repeats"] = reps
            entry["muse_majority"] = majority[0][0] if majority else None
            entry["muse_correct_rate"] = round(
                sum(1 for r in reps if r["correct"]) / len(reps), 4)
            entry["muse_recall_mean"] = round(
                sum(r["must_recall"] for r in reps) / len(reps), 4)
            reader.session_id = run_session
        rows[task.task_id] = entry
        print(f"{task.task_id}: declared={declared.work_type} "
              f"kw={keyword.work_type}({'ok' if entry['keyword_correct'] else 'xx'}) "
              f"muse={inferred.work_type}({'ok' if entry['muse_correct'] else 'xx'}) "
              f"recall d={entry['declared_must_recall']:.3f} "
              f"kw={entry['keyword_must_recall']:.3f} "
              f"muse={entry['muse_must_recall']:.3f}")

    n = len(rows)
    summary = {
        "keyword_work_type_accuracy": round(
            sum(1 for r in rows.values() if r["keyword_correct"]) / n, 4),
        "declared_mean_must_recall": round(
            sum(r["declared_must_recall"] for r in rows.values()) / n, 4),
        "keyword_mean_must_recall": round(
            sum(r["keyword_must_recall"] for r in rows.values()) / n, 4),
        "muse_work_type_accuracy": round(
            sum(1 for r in rows.values() if r["muse_correct"]) / n, 4),
        "muse_mean_must_recall": round(
            sum(r["muse_must_recall"] for r in rows.values()) / n, 4),
    }
    if args.repeats > 1:
        summary["muse_majority_accuracy"] = round(
            sum(1 for r in rows.values()
                if r.get("muse_majority") == r["declared_work_type"]) / n, 4)
        summary["muse_mean_correct_rate"] = round(
            sum(r.get("muse_correct_rate", 0.0) for r in rows.values()) / n, 4)
        summary["muse_recall_mean_over_repeats"] = round(
            sum(r.get("muse_recall_mean", 0.0) for r in rows.values()) / n, 4)
    (outdir / "per_task.json").write_text(json.dumps(rows, indent=2))
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    (outdir / "muse_calls.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n"
                for r in reader.records))
    host = urlparse(OpenCodeModel().base_url).netloc or "opencode.ai"
    manifest = {
        "suite": "SR-2 frame-inference transfer",
        "source": SOURCE_RUN,
        "run_id": outdir.name,
        "created_at": stamp,
        "corpus_digest": corpus_digest(),
        "policy_version": POLICY_VERSION,
        "project_frame_schema": PROJECT_FRAME_SCHEMA,
        "work_frame_schema": WORK_FRAME_SCHEMA,
        "budget_tokens": args.budget,
        "retriever": ("lexical-only (deviation: --no-embeddings)"
                      if args.no_embeddings else "bm25+ollama:bge-m3+rrf60"),
        "reader": reader.name,
        "reader_provider": "opencode-zen-go",
        "reader_model": model,
        "reader_backend": f"opencode-responses ({host})",
        "reasoning_effort": effort,
        "temperature": args.temperature,
        "max_output_tokens": args.max_tokens,
        "session_id": run_session,
        "session_scheme": ("unique-per-call" if args.repeats > 1
                           else "per-run"),
        "repeats": args.repeats,
        "parser": "context_frames.frames (unchanged; same fallback rules)",
        "code_commit": _commit(),
        "muse_usage_totals": reader.totals,
        "cost": "not computed",
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {outdir}")
    print("summary:", json.dumps(summary))
    print("muse usage totals:", reader.totals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
