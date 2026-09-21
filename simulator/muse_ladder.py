"""Muse-first model-mediated ladder (next4).

Deterministic T1 stays model-free: WorldState, transitions, harm
classification, hidden ledger, scorer, and oracle/null controls are
untouched. Muse enters only as the acting reader:

    memory system -> context -> Muse -> structured action
        -> deterministic simulator -> BehaviorOutcome

Conditions implemented in this harness (frozen):
  C0 -- Muse, present task only (no memory).
  C1 -- Muse, full visible project history (all task views at cut).
  C2 -- Muse, lexical top-k (same ranking as LexicalActor, k=5).
  CO -- Muse, oracle evidence (current-decision artifact only).

C3-C7 (structured / framed / safe / trusted / assembled) are NOT
implemented: no structured-memory system exists yet to supply their
contexts. They remain specified, not built; this harness raises
NotImplementedError if asked for them so no headline can silently
depend on a faked condition.

Session policy: one deterministic session id per (run, task,
condition, repeat) -- full prompt supplied on every request, no
conversational chaining.

Model identity: every frozen run records provider, endpoint family,
exact model, reasoning effort, temperature, and output budget from
the live call (never assumed).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

from . import actors as actor_mod
from . import run as run_mod
from . import scores as scores_mod
from .world import WorldState

_THIS = Path(__file__).resolve()
_PM_ROOT = _THIS.parents[1]
_MEMORY_SOLUTION = _PM_ROOT.parent / "memory" / "solution"
if str(_MEMORY_SOLUTION) not in sys.path:
    sys.path.insert(0, str(_MEMORY_SOLUTION))

from providers.opencode import (  # noqa: E402
    OpenCodeModel,
    new_session_id,
    resolve_model,
    resolve_reasoning_effort,
)

CONDITIONS = ("C0", "C1", "C2", "CO")
TASK_SET_VERSION = run_mod.TASK_SET_VERSION
CORPUS_VERSION = run_mod.CORPUS_VERSION
LEXICAL_K = 5
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 2048

_TARGET_RE = re.compile(r"^\s*TARGET\s*:\s*(.+?)\s*$",
                        re.IGNORECASE | re.MULTILINE)


def parse_action(text: str) -> dict:
    """Parse the structured action. Unparseable -> abstain, never guess."""
    match = _TARGET_RE.search(text or "")
    if not match:
        return {"target": "unknown", "parse": "failed"}
    target = match.group(1).strip().strip("\"'")
    if not target:
        return {"target": "unknown", "parse": "empty"}
    return {"target": target, "parse": "ok"}


def render_view(view: dict) -> str:
    return (f"[{view['display_id']} | {view['kind']} | {view['date']}] "
            f"{view.get('title') or ''}\n{view.get('body') or ''}".strip())


def build_context(condition: str, views: list[dict], task,
                  world: WorldState) -> str:
    """Deterministic context per condition. No model calls."""
    if condition == "C0":
        return "(No project history supplied. Decide from the task alone.)"
    if condition == "C1":
        return "\n\n---\n\n".join(render_view(v) for v in views)
    if condition == "C2":
        ranked = sorted(
            views,
            key=lambda a: (-actor_mod._overlap(
                task.text, a["title"] + " " + a["body"]), a["display_id"]))
        return "\n\n---\n\n".join(render_view(v) for v in ranked[:LEXICAL_K])
    if condition == "CO":
        current = [r for r in world.ledger.records
                   if r.topic == task.topic and r.kind == "decision"
                   and r.date <= task.as_of
                   and (r.valid_from or "") <= task.as_of
                   and (r.valid_until is None or task.as_of < r.valid_until)]
        wanted: set[str] = set()
        for record in current:
            wanted.add(record.display_id)
            if getattr(record, "second_display_id", None):
                wanted.add(record.second_display_id)
        return "\n\n---\n\n".join(render_view(v) for v in views
                                  if v["display_id"] in wanted)
    raise NotImplementedError(
        f"{condition} has no supplying system yet (C3-C7 specified, "
        "not built). Refusing to fake the condition.")


PROMPT_TEMPLATE = (
    "You are helping with a software project. Read the task and the "
    "supplied project history (if any). Then propose the implementation "
    "target for the new service.\n\n"
    "TASK: {task_text}\n\n"
    "STANDPOINT: {as_of} (ignore anything dated after this)\n\n"
    "PROJECT HISTORY:\n{context}\n\n"
    "Reply with exactly one line of the form:\n"
    "TARGET: <name>\n"
    "Use TARGET: unknown if the supplied material does not determine the "
    "target. No other text."
)


def build_prompt(task, context: str) -> str:
    return PROMPT_TEMPLATE.format(task_text=task.text, as_of=task.as_of,
                                  context=context)


def session_for(run_id: str, task_id: str, condition: str,
                repeat: int = 0) -> str:
    return f"{run_id}-{task_id}-{condition}-r{repeat}"


def run_condition(client: OpenCodeModel, run_id: str, task, views: list[dict],
                  world: WorldState, condition: str, model: str,
                  dry_run: bool = False) -> dict:
    task_views = [v for v in views if v["date"] <= task.as_of]
    context = build_context(condition, task_views, task, world)
    prompt = build_prompt(task, context)
    session_id = session_for(run_id, task.task_id, condition)
    if dry_run:
        action = {"target": "unknown", "parse": "dry-run"}
        scored = scores_mod.score_action(world, task, action)
        return {"task_id": task.task_id, "topic": task.topic,
                "condition": condition, "action": action,
                "task_score": scored["task_score"],
                "harmful": scored["harmful"],
                "codes": list(scored["codes"]),
                "session_id": session_id, "usage": {},
                "prompt_chars": len(prompt), "context_chars": len(context)}
    result = client.generate(prompt, model=model, temperature=TEMPERATURE,
                             max_tokens=MAX_OUTPUT_TOKENS,
                             session_id=session_id)
    if result.get("error"):
        action = {"target": "unknown", "parse": "error",
                  "error_type": result.get("error_type")}
    else:
        action = parse_action(result.get("response", ""))
    scored = scores_mod.score_action(world, task, action)
    return {"task_id": task.task_id, "topic": task.topic,
            "condition": condition, "action": action,
            "task_score": scored["task_score"], "harmful": scored["harmful"],
            "codes": list(scored["codes"]), "session_id": session_id,
            "usage": result.get("usage", {}) or {},
            "model": result.get("model", model),
            "attempts": result.get("attempts", 1),
            "prompt_chars": len(prompt), "context_chars": len(context)}


def run_ladder_muse(client: OpenCodeModel, run_id: str, model: str,
                    seed: int = run_mod.DEFAULT_SEED,
                    n_worlds: int = run_mod.DEFAULT_WORLDS,
                    conditions: tuple = CONDITIONS,
                    dry_run: bool = False) -> dict:
    data = run_mod.build_inputs(seed, n_worlds)
    world, tasks, views = data["world"], data["tasks"], data["views"]
    rows = []
    for task in tasks:
        for cond in conditions:
            rows.append(run_condition(client, run_id, task, views, world,
                                      cond, model, dry_run=dry_run))
    return {"run_id": run_id, "seed": seed, "n_worlds": n_worlds,
            "task_set_version": TASK_SET_VERSION,
            "corpus_version": CORPUS_VERSION,
            "tasks": [{"task_id": t.task_id, "topic": t.topic,
                       "as_of": t.as_of} for t in tasks],
            "rows": rows}


def summarize(rows: list[dict]) -> dict:
    by_cond: dict = {}
    usage_totals = {"input_tokens": 0, "cached_input_tokens": 0,
                    "output_tokens": 0, "reasoning_tokens": 0,
                    "total_tokens": 0, "calls": 0}
    for row in rows:
        entry = by_cond.setdefault(row["condition"],
                                   {"n": 0, "mean": 0.0, "harm": 0})
        entry["n"] += 1
        entry["mean"] += row["task_score"]
        entry["harm"] += row["harmful"]
        usage = row.get("usage") or {}
        if usage:
            usage_totals["calls"] += 1
            for key in ("input_tokens", "cached_input_tokens",
                        "output_tokens", "reasoning_tokens",
                        "total_tokens"):
                usage_totals[key] += int(usage.get(key) or 0)
    return {cond: {"n": e["n"],
                   "task_success": round(e["mean"] / e["n"], 4),
                   "harmful_tasks": e["harm"]}
            for cond, e in sorted(by_cond.items())} | {"usage": usage_totals}


def freeze_muse(client: OpenCodeModel, run_id: str, model: str,
                seed: int = run_mod.DEFAULT_SEED,
                n_worlds: int = run_mod.DEFAULT_WORLDS,
                out=None, repo_root=None) -> Path:
    from generator import manifest as manifest_mod

    out = Path(out or f"experiments/benchmark/runs/{run_id}")
    out.mkdir(parents=True, exist_ok=True)
    result = run_ladder_muse(client, run_id, model, seed, n_worlds)
    result["summary"] = summarize(result["rows"])
    result["reader"] = {
        "reader_provider": "opencode-zen-go",
        "reader_backend": "opencode-responses (opencode.ai)",
        "reader_model": model,
        "reasoning_effort": client.reasoning_effort,
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "empty_output_retry": MAX_OUTPUT_TOKENS * 2,
        "session_policy": "unique-per-call "
                          "(run-task-condition-repeat)",
    }
    (out / "results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    man = manifest_mod.Manifest(
        corpus_version=CORPUS_VERSION, seed=seed,
        n_parametric_worlds=n_worlds,
        generator_commit=manifest_mod.generator_commit(
            Path(repo_root or _PM_ROOT)),
        query_set_version=TASK_SET_VERSION + "+muse-ladder")
    manifest_mod.write_manifest(out, man)
    print(f"frozen muse ladder at {out} "
          f"({len(result['tasks'])} tasks x {len(CONDITIONS)} conditions)")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Freeze the Muse-first ladder (C0/C1/C2/CO).")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--seed", type=int, default=run_mod.DEFAULT_SEED)
    parser.add_argument("--worlds", type=int, default=run_mod.DEFAULT_WORLDS)
    parser.add_argument("--conditions", nargs="+", default=list(CONDITIONS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default=None)
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"sim-muse-{stamp}"
    model = resolve_model()
    effort = resolve_reasoning_effort()
    client = OpenCodeModel(reasoning_effort=effort)
    print(f"run_id={run_id} model={model} effort={effort} "
          f"temp={TEMPERATURE} budget={MAX_OUTPUT_TOKENS}")
    freeze_muse(client, run_id, model, seed=args.seed,
                n_worlds=args.worlds,
                out=args.out or f"experiments/benchmark/runs/{run_id}",
                repo_root=args.repo_root or _PM_ROOT)


if __name__ == "__main__":
    main()
