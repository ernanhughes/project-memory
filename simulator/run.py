"""Baseline action ladder with frozen runs (T2).

Conditions are rule-based actors over the same tasks: null (no
memory), oracle (ledger ceiling), lexical (unsafe retrieval
baseline), superseded and preference (intervention probes). Each
frozen run records seed, commit, per-task actions and scores, and
per-file checksums. Overlaid ledgers never freeze: interventions are
evaluator-side probes, documented in tests, not freezable corpora.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from generator import build
from generator import manifest as manifest_mod

from . import actors as actor_mod
from . import scores as scores_mod
from . import tasks as tasks_mod
from .world import WorldState

CORPUS_VERSION = "v0.1"
TASK_SET_VERSION = "sim-v0.1-new-service"
DEFAULT_SEED = 20240823
DEFAULT_WORLDS = 12

CONDITIONS = ("null", "oracle", "lexical", "superseded", "preference")


def build_inputs(seed: int = DEFAULT_SEED,
                 n_worlds: int = DEFAULT_WORLDS) -> dict:
    """Ledger + artifacts + tasks. Deterministic in (seed, n_worlds)."""
    built = build.build_corpus(seed=seed, n_worlds=n_worlds)
    world = WorldState(built["ledger"], tasks_mod.TASK_CUT)
    topics = sorted({r.topic for r in built["ledger"].records})
    tasks = tasks_mod.build_tasks(world, topics)
    views = [actor_mod.artifact_view(a) for a in built["artifacts"]]
    views = [v for v in views if v["date"] <= tasks_mod.TASK_CUT]
    return {"ledger": built["ledger"], "world": world, "tasks": tasks,
            "views": views}


def run_ladder(seed: int = DEFAULT_SEED,
               n_worlds: int = DEFAULT_WORLDS) -> dict:
    """Run every condition over every task. Pure data; no file IO."""
    data = build_inputs(seed, n_worlds)
    world, tasks, views = data["world"], data["tasks"], data["views"]
    makers = {
        "null": actor_mod.NullActor,
        "oracle": lambda: actor_mod.OracleActor(world),
        "lexical": actor_mod.LexicalActor,
        "superseded": lambda: actor_mod.SupersededActor(world),
        "preference": lambda: actor_mod.PreferenceActor(world),
    }
    rows = []
    for task in tasks:
        task_views = [v for v in views if v["date"] <= task.as_of]
        for cond in CONDITIONS:
            actor = makers[cond]()
            action = actor.act(task_views, task)
            scored = scores_mod.score_action(world, task, action)
            rows.append({"task_id": task.task_id, "topic": task.topic,
                         "condition": cond, "action": action,
                         "task_score": scored["task_score"],
                         "harmful": scored["harmful"],
                         "codes": list(scored["codes"])})
    return {"seed": seed, "n_worlds": n_worlds, "tasks": [
        {"task_id": t.task_id, "topic": t.topic, "as_of": t.as_of}
        for t in tasks], "rows": rows}


def summarize(rows: list[dict]) -> dict:
    by_cond: dict = {}
    for row in rows:
        entry = by_cond.setdefault(row["condition"], {"n": 0, "mean": 0.0,
                                                      "harm": 0})
        entry["n"] += 1
        entry["mean"] += row["task_score"]
        entry["harm"] += row["harmful"]
    return {cond: {"n": e["n"], "task_success": round(e["mean"] / e["n"], 4),
                   "harmful_tasks": e["harm"]}
            for cond, e in sorted(by_cond.items())}


def freeze(seed: int = DEFAULT_SEED, n_worlds: int = DEFAULT_WORLDS,
           out: str | Path = "experiments/benchmark/runs/sim-v0.1",
           repo_root: str | Path = ".") -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    result = run_ladder(seed, n_worlds)
    result["summary"] = summarize(result["rows"])
    (out / "results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    man = manifest_mod.Manifest(
        corpus_version=CORPUS_VERSION,
        seed=seed,
        n_parametric_worlds=n_worlds,
        generator_commit=manifest_mod.generator_commit(Path(repo_root)),
        query_set_version=TASK_SET_VERSION)
    manifest_mod.write_manifest(out, man)
    print(f"frozen sim run at {out} "
          f"({len(result['tasks'])} tasks x {len(CONDITIONS)} conditions)")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Freeze the sim ladder.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--worlds", type=int, default=DEFAULT_WORLDS)
    parser.add_argument("--out",
                        default="experiments/benchmark/runs/sim-v0.1")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    freeze(seed=args.seed, n_worlds=args.worlds, out=args.out,
           repo_root=args.repo_root)


if __name__ == "__main__":
    main()
