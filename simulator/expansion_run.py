"""Held-out generalization expansion runner (capstone).

Runs the frozen integrated policy v1 plus baselines over Q-tasks,
recall/overload/revocation/conflict probes, and action tasks with
E-conditions. Q-flow tasks use id/yes-no/echo prompts scored
deterministically (qeval); action-flow tasks use the TARGET prompt
scored by the deterministic sim scorer. No LLM judges anywhere.

Condition sets (pre-registered):
  action tasks (task-*): E0 (no memory), E1 (lexical top-5),
    E2 (integrated v1 + S2), EA (A6 rule), EO (decisive-only).
  Q-tasks (eq-*): QE0/QE1/QE2 (Q-flow) + EO (expected-set render;
    skipped for echo control).
  probes (eq-ol/rv/cx): probe context + E2.
  Q6 selection: deterministic pseudo-rows (no reader calls).

Everything unlisted is out of scope for this wave (Q6 corpus
expansion, real-corpus validation, C3-C7 retuning — all refused).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_PM_ROOT = _THIS.parents[1]

from simulator import assembly as asm_mod  # noqa: E402
from simulator import expansion as exp_mod  # noqa: E402
from simulator import pipeline as pipe_mod  # noqa: E402
from simulator import qeval as qeval_mod  # noqa: E402
from simulator import run as run_mod  # noqa: E402
from simulator.muse_ladder import (  # noqa: E402
    LEXICAL_K,
    MAX_OUTPUT_TOKENS,
    TEMPERATURE,
    build_prompt,
    parse_action,
    render_view,
    session_for,
    summarize,
)
from simulator.actors import rank_lexical_views  # noqa: E402
from simulator import scores as scores_mod  # noqa: E402

POLICY_VERSION = pipe_mod.POLICY_VERSION


def _task_views(views, as_of: str) -> list:
    return [v for v in views if v["date"] <= as_of]


def _render(units: list) -> str:
    return "\n\n---\n\n".join(render_view(v) for v in units)


# -- action-flow E-contexts -------------------------------------------------

def action_contexts(task, views: list, world) -> dict:
    """E0/E1/E2/EA/EO strings for one action task. Deterministic."""
    tv = _task_views(views, task.as_of)
    admitted, _trace = pipe_mod.integrated_views(tv, world, task)
    by_id = {v["display_id"] for v in admitted}
    from simulator import frames as frames_mod
    decisive = {d for d in frames_mod.decisive_ids(
        world, task.topic, task.as_of) if d in by_id}
    dec_views = [v for v in admitted if v["display_id"] in decisive]
    sup_views, _ = asm_mod.select_support_overlap(
        admitted, decisive, task.text)
    sup_views = [v for v in sup_views
                 if v["display_id"] not in decisive]
    # EA: A6 rule (group + budget over admitted).
    from simulator import assembly as _asm
    red, _ = _asm.collapse_redundant(admitted, _derived_map(
        admitted, world))
    grouped = _asm.group_order(red, decisive, set())
    budgeted, _ = _asm.apply_budget(grouped, decisive)
    return {
        "E0": "",
        "E1": _render(rank_lexical_views(tv, task.text)[:LEXICAL_K]),
        "E2": _render(dec_views + sup_views),
        "EA": _render(budgeted),
        "EO": _render(dec_views),
    }


def _derived_map(admitted: list, world) -> dict:
    by_key = {r.key: r for r in world.ledger.records}
    out = {}
    for view in admitted:
        for record in world.ledger.records:
            if (record.display_id == view["display_id"]
                    or record.second_display_id == view["display_id"]):
                if record.kind == "derived_restatement":
                    roots = []
                    stack = list(record.derived_from or ())
                    seen: set[str] = set()
                    while stack:
                        key = stack.pop()
                        if key in seen:
                            continue
                        seen.add(key)
                        src = by_key.get(key)
                        if src is None or not src.display_id:
                            continue
                        if src.kind != "derived_restatement":
                            roots.append(src.display_id)
                        else:
                            stack.extend(src.derived_from or ())
                    out[view["display_id"]] = (
                        tuple(roots), record.content)
    return out


# -- Q-flow ------------------------------------------------------------------

def q_contexts(qtask, views: list, world) -> dict:
    """QE0/QE1/QE2/EO strings for one Q-task. EO skipped (None) where
    the oracle is the empty query itself (echo control)."""
    tv = _task_views(views, qtask.as_of)
    admitted, _trace = pipe_mod.integrated_views(tv, world, qtask)
    by_display = {v["display_id"]: v for v in views}
    out = {
        "QE0": "",
        "QE1": _render(rank_lexical_views(tv, qtask.text)[:LEXICAL_K]),
        "QE2": _render(admitted),
        "EO": None,
    }
    if qtask.query_kind == "ids":
        units = [by_display[did] for did in qtask.expected_ids
                 if did in by_display]
        out["EO"] = _render(units)
    elif qtask.query_kind == "yesno":
        dec_ids, prod_ids = set(), set()
        for record in world.ledger.records:
            if record.date > qtask.as_of:
                continue
            if record.kind == "decision" and (
                    record.valid_from or "") <= qtask.as_of:
                if record.display_id:
                    dec_ids.add(record.display_id)
            if (record.kind == "production_state"
                    and (record.valid_from or "") <= qtask.as_of
                    and (record.valid_until is None
                         or qtask.as_of < record.valid_until)):
                if record.display_id:
                    prod_ids.add(record.display_id)
        units = [by_display[d] for d in sorted(dec_ids | prod_ids)
                 if d in by_display]
        out["EO"] = _render(units)
    return out


def q6_rows(world, topics: list[str], as_of: str,
            views: list, run_id: str) -> list[dict]:
    """Deterministic selection rows (no reader): E2-admitted ids vs
    oracle set precision/recall, score = F1."""
    from simulator import pipeline as _pipe
    rows = []
    for topic in topics:
        tv = [v for v in views if v["date"] <= as_of]
        admitted, _trace = _pipe.integrated_views(tv, world, _fake_task(
            topic, as_of))
        pred = {v["display_id"] for v in admitted}
        exp = exp_mod.oracle_selection_set(world.ledger, topic, as_of)
        pr = qeval_mod.precision_recall(pred, exp)
        f1 = (round(2 * pr["precision"] * pr["recall"]
                    / (pr["precision"] + pr["recall"]), 4)
              if pr["precision"] and pr["recall"] else 0.0)
        rows.append({"task_id": f"eq-q6-{topic[:12]}", "topic": topic,
                     "condition": "Q6SEL",
                     "action": {"precision": pr["precision"],
                                "recall": pr["recall"]},
                     "task_score": f1, "harmful": 0,
                     "codes": ("q6.selection",),
                     "session_id": "n/a-deterministic",
                     "usage": {}, "prompt_chars": 0,
                     "context_chars": sum(
                         len(v.get("title", ""))
                         + len(v.get("body", "")) for v in admitted)})
    return rows


class _FakeTask:
    def __init__(self, topic, as_of):
        self.task_id = f"q6-{topic[:12]}"
        self.topic = topic
        self.text = topic
        self.as_of = as_of
        self.project = "main"


def _fake_task(topic, as_of):
    return _FakeTask(topic, as_of)


# -- probe contexts (action-flow, TARGET scoring) ------------------------------

def probe_rows(task, views: list, world, client, run_id: str, model: str,
               dry_run: bool) -> list[dict]:
    """OL/RV/CX-style probe: custom context + E2, both live."""
    from simulator import scores as _scores
    tv = _task_views(views, task.as_of)
    out = []
    if task.task_id.startswith("eq-ol"):
        customs = {"OL": exp_mod.overload_views(task, tv, world)}
    elif task.task_id.startswith("eq-rv"):
        pool, meta = exp_mod.revocation_probe(task, tv, world)
        assert pool is not None
        customs = {"RV": pool}
    elif task.task_id.startswith("eq-cx"):
        pool, _note = exp_mod.conflict_views(task, tv, world)
        assert pool is not None
        customs = {"CX": pool}
    else:
        raise ValueError(task.task_id)
    contexts = {name: _render(pool) for name, pool in customs.items()}
    contexts["E2"] = _render_assembled_e2(task, tv, world)
    for cond, context in contexts.items():
        out.append(_target_row(client, run_id, task, world, cond,
                               context, model, dry_run))
    return out


def _revoked_for(task, world) -> list[str]:
    from simulator import wrong_memory as wm_mod
    cur = wm_mod.current_decision(world, task.topic, task.as_of)
    if cur is not None:
        for key in cur.supported_by:
            rec = world.ledger.by_key().get(key)
            if rec is not None and rec.kind == "evidence":
                return [rec.display_id]
    return []


def _render_assembled_e2(task, tv, world) -> str:
    from simulator import assembly as _asm
    from simulator import frames as _frames
    by_id = {v["display_id"] for v in tv}
    integrated, _t = pipe_mod.integrated_views(
        tv, world, task,
        meta={"revoked": _revoked_for(task, world)}
        if task.task_id.startswith("eq-rv") else None)
    decisive = {d for d in _frames.decisive_ids(
        world, task.topic, task.as_of)
        if d in {v["display_id"] for v in integrated}}
    dec = [v for v in integrated if v["display_id"] in decisive]
    sup, _s = _asm.select_support_overlap(
        integrated, decisive, task.text)
    sup = [v for v in sup if v["display_id"] not in decisive]
    return _render(dec + sup)


def q_rows(qtask, views: list, world, client, run_id: str, model: str,
         dry_run: bool) -> list[dict]:
    """Q-flow rows: QE0/QE1/QE2 live (or dry) + EO reference + skip
    notes. Scored deterministically by qeval, never by a judge."""
    from simulator import muse_ladder as ml
    contexts = q_contexts(qtask, views, world)
    rows = []
    for cond in ("QE0", "QE1", "QE2"):
        rows.append(_q_row(client, run_id, qtask, cond,
                           contexts[cond], model, dry_run))
    eo = contexts["EO"]
    if eo is not None:
        rows.append(_q_row(client, run_id, qtask, "EO", eo, model,
                           dry_run))
    else:
        rows.append({"task_id": qtask.task_id, "topic": qtask.topic,
                     "condition": "EO", "action": {"parsed": None},
                     "task_score": None, "harmful": 0,
                     "codes": ("qecho-oracle-is-query",),
                     "skipped": "echo oracle is the empty query",
                     "session_id": ml.session_for(
                         run_id, qtask.task_id, "EO"),
                     "usage": {}, "prompt_chars": 0, "context_chars": 0})
    return rows


def _q_row(client, run_id: str, qtask, condition: str, context: str,
           model: str, dry_run: bool) -> dict:
    from simulator import muse_ladder as ml
    prompt = qeval_mod.build_q_prompt(qtask, context)
    session_id = ml.session_for(run_id, qtask.task_id, condition)
    if dry_run:
        scored = {"task_score": 0.0, "parsed": "dry-run",
                  "expected": None}
        return {"task_id": qtask.task_id, "topic": qtask.topic,
                "condition": condition, "action": scored,
                "task_score": scored["task_score"], "harmful": 0,
                "codes": ("qeval-dry",), "session_id": session_id,
                "usage": {}, "prompt_chars": len(prompt),
                "context_chars": len(context)}
    result = client.generate(
        prompt, model=model, temperature=ml.TEMPERATURE,
        max_tokens=ml.MAX_OUTPUT_TOKENS, session_id=session_id)
    if result.get("error"):
        scored = {"task_score": 0.0, "parsed": None,
                  "error_type": result.get("error_type")}
    else:
        scored = qeval_mod.score_qtask(
            qtask, result.get("response", ""))
    return {"task_id": qtask.task_id, "topic": qtask.topic,
            "condition": condition, "action": scored,
            "task_score": scored["task_score"], "harmful": 0,
            "codes": ("qeval-scored",), "session_id": session_id,
            "usage": result.get("usage", {}) or {},
            "model": result.get("model", model),
            "attempts": result.get("attempts", 1),
            "prompt_chars": len(prompt),
            "context_chars": len(context)}


def _target_row(client, run_id: str, task, world, condition: str,
                context: str, model: str, dry_run: bool) -> dict:
    from simulator import muse_ladder as ml
    from simulator import scores as _scores
    prompt = ml.build_prompt(task, context)
    session_id = ml.session_for(run_id, task.task_id, condition)
    if dry_run:
        action = {"target": "unknown", "parse": "dry-run"}
        scored = _scores.score_action(world, task, action)
        return {"task_id": task.task_id, "topic": task.topic,
                "condition": condition, "action": action,
                "task_score": scored["task_score"],
                "harmful": scored["harmful"],
                "codes": list(scored["codes"]),
                "session_id": session_id, "usage": {},
                "prompt_chars": len(prompt),
                "context_chars": len(context)}
    result = client.generate(
        prompt, model=model, temperature=ml.TEMPERATURE,
        max_tokens=ml.MAX_OUTPUT_TOKENS, session_id=session_id)
    if result.get("error"):
        action = {"target": "unknown", "parse": "error",
                  "error_type": result.get("error_type")}
    else:
        action = ml.parse_action(result.get("response", ""))
    scored = _scores.score_action(world, task, action)
    return {"task_id": task.task_id, "topic": task.topic,
            "condition": condition, "action": action,
            "task_score": scored["task_score"],
            "harmful": scored["harmful"],
            "codes": list(scored["codes"]), "session_id": session_id,
            "usage": result.get("usage", {}) or {},
            "model": result.get("model", model),
            "attempts": result.get("attempts", 1),
            "prompt_chars": len(prompt),
            "context_chars": len(context)}


def action_rows(task, views: list, world, client, run_id: str,
                model: str, dry_run: bool) -> list[dict]:
    """E0/E1/E2/EA/EO rows for one action task (TARGET flow)."""
    contexts = action_contexts(task, views, world)
    return [_target_row(client, run_id, task, world, cond,
                        contexts[cond], model, dry_run)
            for cond in ("E0", "E1", "E2", "EA", "EO")]


def probe_action_rows(task, views: list, world, client, run_id: str,
                      model: str, dry_run: bool) -> list[dict]:
    """OL/RV/CX probe rows: custom context + E2 (TARGET flow)."""
    from simulator import expansion as _exp
    tv = _task_views(views, task.as_of)
    out = []
    if task.task_id.startswith("eq-ol"):
        customs = {"OL": _exp.overload_views(task, tv, world)}
    elif task.task_id.startswith("eq-rv"):
        pool, meta = _exp.revocation_probe(task, tv, world)
        assert pool is not None
        customs = {"RV": pool}
    elif task.task_id.startswith("eq-cx"):
        pool, _note = _exp.conflict_views(task, tv, world)
        assert pool is not None
        customs = {"CX": pool}
    else:
        raise ValueError(task.task_id)
    e2units, _trace = pipe_mod.integrated_views(
        tv, world, task,
        meta={"revoked": _revoked_for(task, world)}
        if task.task_id.startswith("eq-rv") else None)
    contexts = {name: _render(pool) for name, pool in customs.items()}
    contexts["E2"] = _render_assembled_e2(task, tv, world)
    for cond, context in contexts.items():
        out.append(_target_row(client, run_id, task, world, cond,
                               context, model, dry_run))
    return out


def summarize_expansion(rows: list[dict]) -> dict:
    from simulator import muse_ladder as ml
    return ml.summarize(rows)


def _muse_client(args, outdir: Path):
    from providers.opencode import (OpenCodeModel, resolve_api_key,
                                    resolve_model,
                                    resolve_reasoning_effort)
    muse_model = resolve_model(None)
    muse_effort = resolve_reasoning_effort(args.reasoning_effort)
    backend = OpenCodeModel()
    if not resolve_api_key(backend.api_key):
        print("no Muse credentials; aborting (no live calls made)")
        raise SystemExit(2)
    return backend, muse_model, muse_effort


def _manifest_extra(args, muse_model: str, muse_effort: str,
                    outdir: Path, totals: dict) -> dict:
    from simulator import muse_ladder as ml
    memory_root = ml._MEMORY_SOLUTION.parent
    return {
        "reader": f"opencode:{muse_model}@t0",
        "reader_provider": "opencode-zen-go",
        "reader_model": muse_model,
        "reasoning_effort": muse_effort,
        "temperature": ml.TEMPERATURE,
        "max_output_tokens": ml.MAX_OUTPUT_TOKENS,
        "session_policy": "unique-per-call (run-task-condition)",
        "code_commit": ml._git_head(ml._PM_ROOT),
        "provider_source_commit": ml._git_head(memory_root),
        "muse_usage_totals": totals,
    }


def main(argv: list[str] | None = None) -> None:
    import argparse
    from simulator import muse_ladder as ml
    parser = argparse.ArgumentParser(
        description="Freeze the held-out generalization expansion.")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"sim-muse-exp-{stamp}"
    outdir = Path(args.out or f"experiments/benchmark/runs/{run_id}")
    outdir.mkdir(parents=True, exist_ok=True)
    if ml._git_dirty(ml._PM_ROOT):
        print("REFUSING TO FREEZE: project-memory tree dirty.")
        raise SystemExit(1)
    data = run_mod.build_inputs()
    world, sim_tasks, views = (data["world"], data["tasks"],
                               data["views"])
    ledger = data["ledger"]
    backend, muse_model, muse_effort = _muse_client(args, outdir)
    rows: list[dict] = []
    # Action tasks: E0/E1/E2/EA/EO (TARGET flow).
    for task in sim_tasks:
        for cond, context in action_contexts(
                task, views, world).items():
            rows.append(_target_row(
                backend, run_id, task, world, cond, context,
                muse_model, args.dry_run))
    # Q-tasks (Q-flow) + recall + irrelevant.
    for qtask in exp_mod.all_qtasks(ledger):
        rows.extend(q_rows(qtask, views, world, backend, run_id,
                           muse_model, args.dry_run))
    # Probes (TARGET flow).
    for ptask in exp_mod.probe_tasks():
        rows.extend(probe_rows(
            ptask, views, world, backend, run_id, muse_model,
            args.dry_run))
    # Q6 selection (deterministic, no reader).
    for topic in ("event-store backend", "message-queue backend"):
        rows.extend(q6_rows(world, [topic], "2025-06-30", views,
                            run_id))
    summary = summarize_expansion(rows)
    payload = {"run_id": run_id, "tasks": len(sim_tasks),
               "rows": rows, "summary": summary}
    (outdir / "results.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    totals: dict = {}
    for row in rows:
        usage = row.get("usage") or {}
        if usage:
            totals["calls"] = totals.get("calls", 0) + 1
            for key in ("input_tokens", "cached_input_tokens",
                        "output_tokens", "reasoning_tokens",
                        "total_tokens"):
                totals[key] = totals.get(key, 0) + int(
                    usage.get(key, 0) or 0)
    manifest = {
        "suite": "E-expansion-generalization",
        "run_id": run_id,
        "created_at": stamp,
        "split": "held-out-expansion",
        "task_set_version": "sim-v0.1-new-service+expansion-v1",
        "corpus_version": run_mod.CORPUS_VERSION,
        "seed": run_mod.DEFAULT_SEED,
        "policy_version": POLICY_VERSION,
        "trust_policy_version": "trust-policy-v1",
    }
    manifest.update(_manifest_extra(args, muse_model, muse_effort,
                                    outdir, totals))
    from generator import manifest as manifest_mod
    manifest["files"] = manifest_mod.collect_files(outdir)
    (outdir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {outdir} "
          f"({len(rows)} rows, {totals.get('calls', 0)} live calls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
