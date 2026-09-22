"""Session-isolation audit (Test 1): does x-opencode-session carry hidden state?

For strongly memory-dependent tasks (fix-store, cite-rule,
corpus-cleanup), compare B0-no-memory behaviour across arms:

  S0: fresh unique session, B0.
  S1: one session: B4 memory-rich call first, then the EXACT same B0
      input as S0.
  S2: another fresh unique session, B0 again.

Key question: does post-memory B0 (S1b) differ from fresh B0
(S0/S2) in a memory-consistent direction? 3 replicates per task.
Every call is live (no cache): caching would defeat the audit.

Output: experiments/benchmark/runs/sr1b-session-audit-<stamp>-muse/
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

from behavior_eval import contexts as C  # noqa: E402
from behavior_eval import prompts as P  # noqa: E402
from behavior_eval import runner as R  # noqa: E402
from behavior_eval.experiments import (  # noqa: E402
    PLAN,
    _here_units,
    cleanup_entry,
    membership_for,
)
from behavior_eval.tasks import task_by_id  # noqa: E402
from providers.opencode import (  # noqa: E402
    OpenCodeModel,
    resolve_api_key,
    resolve_model,
    resolve_reasoning_effort,
)

AUDIT_TASKS = ("fix-store", "cite-rule", "corpus-cleanup")
REPS = 3


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            text=True).strip()
    except Exception:
        return "unknown"


class AuditClient:
    """Live-only Muse caller; session chosen per call, nothing cached."""

    def __init__(self, model: str, temperature: float, max_tokens: int,
                 effort: str) -> None:
        self.backend = OpenCodeModel()
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.effort = effort
        self.records: list[dict] = []
        self.totals: dict = {}

    def ask(self, prompt: str, session_id: str) -> str:
        result = self.backend.generate(
            f"{P.SYSTEM_PROMPT}\n\n{prompt}",
            model=self.model, temperature=self.temperature,
            max_tokens=self.max_tokens, reasoning_effort=self.effort,
            session_id=session_id)
        if result.get("error"):
            raise RuntimeError(
                f"audit call failed [{result.get('error_type')}] "
                f"session={session_id}: {result.get('error')}")
        usage = result.get("usage") or {}
        for k in ("input_tokens", "cached_input_tokens", "output_tokens",
                  "reasoning_tokens", "total_tokens"):
            self.totals[k] = self.totals.get(k, 0) + int(usage.get(k, 0) or 0)
        self.totals["calls"] = self.totals.get("calls", 0) + 1
        self.records.append({"session_id": session_id,
                             "attempts": result.get("attempts"),
                             "usage": usage})
        return result["response"]


def build_entries(task_id: str):
    """B0/B4 entries built exactly like run_suite (frozen builders)."""
    task = task_by_id(task_id)
    plan = PLAN[task_id]
    texts = C.corpus_texts()
    if task_id == "corpus-cleanup":
        b0 = cleanup_entry("B0")
        b4 = cleanup_entry("B4")
    else:
        b0 = C.finalize(C.build_condition(
            plan["ch10"], "B0", texts, task.decisive_units, (),
            ch10_task=plan["ch10"]))
        b4 = C.finalize(C.build_condition(
            plan["ch10"], "B4", texts, task.decisive_units, (),
            ch10_task=plan["ch10"]))
    membership = membership_for(plan["ch10"], texts)
    return task, texts, plan, membership, b0, b4


def score(task, entry, condition: str, answer: str, repeat: int,
          membership, no_memory_types, reader_name: str) -> dict:
    actions_raw, parse_ok = P.parse_actions(answer, task.action_schema)
    actions = [R.Action.from_dict(a) for a in actions_raw]
    outcome = R.score_outcome(task, actions, answer, parse_ok, entry,
                              condition, repeat, reader_name, membership,
                              no_memory_types)
    return {"actions": [a.action_type for a in actions],
            "parse_ok": parse_ok,
            "task_score": outcome.task_score,
            "failure_classes": list(outcome.failure_classes),
            "dimension_scores": dict(outcome.dimension_scores)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--tasks", default=",".join(AUDIT_TASKS))
    parser.add_argument("--reps", type=int, default=REPS)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    model = resolve_model(args.model)
    effort = resolve_reasoning_effort(args.reasoning_effort)
    task_ids = [t for t in args.tasks.split(",") if t.strip()]
    ncalls = len(task_ids) * args.reps * 4
    if args.dry_run:
        print(f"dry-run: model={model} effort={effort} tasks={task_ids} "
              f"reps={args.reps} live_calls={ncalls} "
              f"key_configured={bool(resolve_api_key())}")
        return 0
    if not resolve_api_key():
        print("no Muse credentials (no live calls made)")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else (
        ROOT / "experiments" / "benchmark" / "runs"
        / f"sr1b-session-audit-{stamp}-muse")
    outdir.mkdir(parents=True, exist_ok=True)
    client = AuditClient(model, args.temperature, args.max_tokens, effort)
    reader_name = f"opencode:{model}@t0"
    rows: list[dict] = []

    for task_id in task_ids:
        task, texts, plan, membership, b0, b4 = build_entries(task_id)
        b0_prompt = P.build_prompt(task, b0["context"])
        b4_prompt = P.build_prompt(task, b4["context"])
        # B0 outcome first (mirrors run_suite pass 1: seeds attribution).
        b0_types: dict[int, list] = {}
        for rep in range(args.reps):
            # S0 fresh-session B0 (also seeds B4 attribution like run_suite).
            s0 = f"memory-sraudit-{task_id}-S0-r{rep}"
            a0 = client.ask(b0_prompt, s0)
            o0 = score(task, b0, "B0", a0, rep, membership, None,
                       reader_name)
            b0_types[rep] = o0["actions"]
            rows.append(_row(task_id, "S0", "B0", rep, s0, b0,
                             b0_prompt, a0, o0, len(client.records) - 1,
                             client))
            # S1: same session, B4 then the exact same B0 input.
            s1 = f"memory-sraudit-{task_id}-S1-r{rep}"
            a4 = client.ask(b4_prompt, s1)
            here = _here_units(task, b4, texts, plan)
            o4 = score(task, b4, "B4", a4, rep, dict(membership, here=here),
                       b0_types[rep], reader_name)
            rows.append(_row(task_id, "S1a", "B4", rep, s1, b4,
                             b4_prompt, a4, o4, len(client.records) - 1,
                             client))
            a1 = client.ask(b0_prompt, s1)
            o1 = score(task, b0, "B0-post-memory", a1, rep, membership,
                       None, reader_name)
            rows.append(_row(task_id, "S1b", "B0", rep, s1, b0,
                             b0_prompt, a1, o1, len(client.records) - 1,
                             client))
            # S2 fresh-session B0 again.
            s2 = f"memory-sraudit-{task_id}-S2-r{rep}"
            a2 = client.ask(b0_prompt, s2)
            o2 = score(task, b0, "B0", a2, rep, membership, None,
                       reader_name)
            rows.append(_row(task_id, "S2", "B0", rep, s2, b0,
                             b0_prompt, a2, o2, len(client.records) - 1,
                             client))
            print(f"{task_id} r{rep}: S0={o0['actions']}/{o0['task_score']} "
                  f"S1a={o4['actions']}/{o4['task_score']} "
                  f"S1b={o1['actions']}/{o1['task_score']} "
                  f"S2={o2['actions']}/{o2['task_score']}")

    (outdir / "rows.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    manifest = {
        "suite": "SR-1b session-isolation audit",
        "run_id": outdir.name,
        "created_at": stamp,
        "tasks": task_ids,
        "reps": args.reps,
        "arms": {"S0": "fresh session B0", "S1a": "session B4",
                 "S1b": "same session, exact S0 B0 input",
                 "S2": "fresh session B0 again"},
        "reader": reader_name,
        "reader_provider": "opencode-zen-go",
        "reader_model": model,
        "reasoning_effort": effort,
        "temperature": args.temperature,
        "max_output_tokens": args.max_tokens,
        "grader_version": "behavior-grader-v2",
        "prompt_version": "behavior-prompt-v2",
        "fixture_version": "behavior-fixtures-v1",
        "code_commit": _commit(),
        "muse_usage_totals": client.totals,
        "cost": "not computed",
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {outdir} totals={client.totals}")
    return 0


def _row(task_id, arm, condition, rep, session, entry, prompt, answer,
         scored, rec_idx, client):
    rec = client.records[rec_idx]
    return {"task": task_id, "arm": arm, "condition": condition,
            "repeat": rep, "session_id": session,
            "context_hash": entry["context_hash"],
            "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:16],
            "attempts": rec["attempts"], "usage": rec["usage"],
            "response": answer, **scored}


if __name__ == "__main__":
    raise SystemExit(main())
