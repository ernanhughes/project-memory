"""Muse strong-reader transfer driver (SR-1) for Chapter 12 behaviour.

Cross-cutting validation wave: the frozen Chapter 12 behavioural
suite through Muse Spark (OpenCode Zen/Go Responses API) instead of
the local Ollama reader. Answers: do the memory mechanisms still
matter when the reader is substantially stronger?

Frozen: corpus, contexts, grader (behavior-grader-v2), prompt
semantics (behavior-prompt-v2), fixtures (behavior-fixtures-v1).
The transfer variable is the reader model only.

Does NOT touch frozen Ollama runs. Output goes to a fresh
``sr1-ch12-<stamp>-muse`` run directory. Decoding is fixed at
temperature 0; reasoning effort is fixed per comparison (default
``low``). Provider errors raise loudly and never enter the grader
as prose. Every Muse call's request metadata, response text, and
usage are frozen to ``muse_calls.jsonl`` (no credentials, no auth
headers).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "solution"))

from behavior_eval import prompts as P  # noqa: E402
from behavior_eval.experiments import (  # noqa: E402
    PLAN,
    REPEAT_CONDS,
    REPEAT_TASKS,
    REPEATS,
    run_suite,
    summarize,
)
from behavior_eval.model import (  # noqa: E402
    BEHAVIOR_SCHEMA_VERSION,
    FIXTURE_VERSION,
    GRADER_VERSION,
)
from behavior_eval.prompts import PROMPT_VERSION  # noqa: E402
from behavior_eval.runner import ReaderClient  # noqa: E402
from providers.opencode import (  # noqa: E402
    DEFAULT_MODEL,
    OpenCodeModel,
    resolve_api_key,
    resolve_model,
    resolve_reasoning_effort,
)

SOURCE_RUN = "ch12-20260920T204414Z-behavior"
CORE_LADDER = ("B2", "B3", "B4", "BO")
INTERVENTIONS = ("BA", "BR", "BW")
EXTRA = ("B1", "B1P", "BS")


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            text=True).strip()
    except Exception:
        return "unknown"


class MuseReaderClient(ReaderClient):
    """ReaderClient over Muse Spark with separated cache identity.

    Cache salt covers provider, model, reasoning effort, and
    temperature (§46), so Muse rows can never collide with Ollama
    rows. Each live call freezes request metadata, response text,
    and usage into ``records`` (§47); cache hits replay the frozen
    response without re-querying.
    """

    def __init__(self, model: str, cache_dir: Path,
                 temperature: float, max_tokens: int,
                 reasoning_effort: str, session_id: str) -> None:
        salt = (f"opencode|{model}|reason-{reasoning_effort}"
                f"|temp-{temperature}")
        super().__init__(f"opencode:{model}", cache_dir, live=None,
                         cache_salt=salt)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.session_id = session_id
        self.backend = OpenCodeModel()
        self.records: list[dict] = []
        self.totals: dict = {}

    @property
    def name(self) -> str:
        return f"opencode:{self.model.split('opencode:', 1)[1]}@t0"

    def ask(self, task, entry: dict, prompt: str,
            condition: str, repeat: int) -> str:
        key = self._cache_key(prompt, repeat)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            self.hits += 1
            return json.loads(path.read_text())["response"]
        self.calls += 1
        full = f"{P.SYSTEM_PROMPT}\n\n{prompt}"
        result = self.backend.generate(
            full,
            model=self.model.split("opencode:", 1)[1],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort,
            # One stable routing session per run (gateway requirement;
            # routing/cache affinity only). Requests stay stateless —
            # full input every call, no chaining — so paired
            # conditions remain independent.
            session_id=self.session_id,
        )
        if result.get("error"):
            raise RuntimeError(
                f"muse reader failed [{result.get('error_type')}] "
                f"on {task.task_id}/{condition}/rep{repeat}: "
                f"{result.get('error')}")
        response = result["response"]
        usage = result.get("usage") or {}
        for k in ("input_tokens", "cached_input_tokens", "output_tokens",
                  "reasoning_tokens", "total_tokens"):
            self.totals[k] = self.totals.get(k, 0) + int(usage.get(k, 0) or 0)
        self.totals["calls"] = self.totals.get("calls", 0) + 1
        self.totals["attempts"] = (self.totals.get("attempts", 0)
                                   + int(result.get("attempts", 1) or 1))
        request = dict(result.get("request") or {})
        self.records.append({
            "task": task.task_id, "condition": condition,
            "repeat": repeat, "context_hash": entry["context_hash"],
            "model": request.get("model"), "temperature": request.get(
                "temperature"),
            "reasoning_effort": request.get("reasoning_effort"),
            "max_output_tokens": request.get("max_output_tokens"),
            "attempts": result.get("attempts"),
            "usage": usage,
            "response": response,
            "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:16],
        })
        path.write_text(json.dumps(
            {"task": task.task_id, "condition": condition,
             "repeat": repeat, "context_hash": entry["context_hash"],
             "prompt": prompt, "response": response,
             "usage": usage, "request": request}))
        return response


def estimate_calls(tasks, conditions: set[str] | None,
                   repeats: bool) -> tuple[int, dict]:
    """Expected live-call count without touching any model (§71)."""
    per_task: dict = {}
    for task in tasks:
        plan = PLAN[task.task_id]
        n = 1  # B0 always runs
        for cond in plan["conds"]:
            if cond == "B0":
                continue
            if conditions is not None and cond not in conditions:
                continue
            n += (REPEATS if repeats and task.task_id in REPEAT_TASKS
                  and cond in REPEAT_CONDS else 1)
        per_task[task.task_id] = n
    return sum(per_task.values()), per_task


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Chapter 12 behaviour suite with Muse Spark.")
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--model", default=None,
                        help="default: $MEMORY_MUSE_MODEL or "
                             f"{DEFAULT_MODEL}")
    parser.add_argument("--no-repeats", action="store_true")
    parser.add_argument("--tasks", default=None,
                        help="comma-separated task subset")
    parser.add_argument("--conditions", default=None,
                        help="comma-separated condition subset "
                             "(B0 always runs); default: full ladder")
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="first-attempt output budget; retry once at 2x "
                             "on empty output (default 2048: reasoning "
                             "traces on long contexts exhaust 1024)")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="verify wiring and manifest shape; no model calls")
    parser.add_argument("--estimate-only", action="store_true",
                        help="print expected call counts; no model calls")
    args = parser.parse_args()

    model = resolve_model(args.model)
    effort = resolve_reasoning_effort(args.reasoning_effort)
    conditions = (set(args.conditions.split(","))
                  if args.conditions else None)

    from behavior_eval.tasks import all_tasks
    tasks = all_tasks()
    if args.tasks:
        want = set(args.tasks.split(","))
        tasks = [t for t in tasks if t.task_id in want]
    if not tasks:
        print("no tasks selected; aborting")
        return 2

    total, per_task = estimate_calls(tasks, conditions,
                                     repeats=not args.no_repeats)
    if args.estimate_only or args.dry_run:
        print(f"model={model} reasoning_effort={effort} "
              f"temperature={args.temperature} max_tokens={args.max_tokens} "
              f"tasks={len(tasks)} key_configured="
              f"{bool(resolve_api_key())}")
        print(f"estimated total calls: {total}")
        for tid, n in per_task.items():
            print(f"  {tid}: {n} calls")
        return 0

    if not resolve_api_key():
        print("no Muse credentials; set MEMORY_OPENCODE_API_KEY or "
              "OPENCODE_ZEN_API_KEY (no live calls made)")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else (
        ROOT / "experiments" / "benchmark" / "runs"
        / f"sr1-ch12-{stamp}-muse")
    cache_dir = outdir / "reader-cache"
    outdir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(exist_ok=True)
    # Stable per-run routing session (gateway requirement). Frozen in
    # the manifest; requests remain stateless (full input, no chaining).
    run_session = f"memory-{outdir.name}"
    client = MuseReaderClient(model, cache_dir, args.temperature,
                              args.max_tokens, effort, run_session)

    resume = None
    prior = outdir / "conditions.json"
    if prior.exists():
        resume = json.loads(prior.read_text())
        print(f"resuming: {sum(len(v) for v in resume.values())} "
              f"stored rows reused when context hashes match")

    suite = run_suite(client, tasks, repeats=not args.no_repeats,
                      resume=resume, conditions=conditions)
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
    calls_path = outdir / "muse_calls.jsonl"
    prior_records = []
    if calls_path.exists():
        prior_records = [
            json.loads(line) for line in calls_path.read_text().splitlines()
            if line.strip()]
    seen = {(r.get("task"), r.get("condition"), r.get("repeat"))
            for r in prior_records}
    prior_records.extend(
        r for r in client.records
        if (r.get("task"), r.get("condition"), r.get("repeat")) not in seen)
    calls_path.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n"
                for r in prior_records))
    host = urlparse(OpenCodeModel().base_url).netloc or "opencode.ai"
    manifest = {
        "suite": "SR-1 strong-reader transfer",
        "source": SOURCE_RUN,
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
        "reader_provider": "opencode-zen-go",
        "reader_model": model,
        "reader_backend": f"opencode-responses ({host})",
        "reasoning_effort": effort,
        "temperature": args.temperature,
        "max_output_tokens": args.max_tokens,
        "output_retry": "once at 2x on empty output",
        "session_id": run_session,
        "conditions_run": sorted(conditions) if conditions else "full ladder",
        "ch10_source_run": "ch10-20260920T163314Z-context-frames",
        "ch11_source_run": "ch11-20260920T171039Z-derived-loops",
        "ch14_source_run": "ch14-20260920T174259Z-context-assembly",
        "token_estimator": "chars//4 (estimated tokens)",
        "code_commit": _commit(),
        "reader_cache_calls": client.calls,
        "reader_cache_hits": client.hits,
        "muse_usage_totals": client.totals,
        "cost": "not computed",
        # No credentials, auth headers, or raw provider payloads here.
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"wrote {outdir}  calls={client.calls} hits={client.hits}")
    for cond, stats in summary["mean_by_condition"].items():
        print(f"  {cond}: success={stats['task_success']} "
              f"harmful={stats['harmful']} n={stats['n']}")
    print("influence:", summary["influence"]["counts"])
    print("muse usage totals:", client.totals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
