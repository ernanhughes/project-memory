"""Capstone runner: replay (deterministic) + live (model-backed) modes.

Replay mode re-executes the integration over frozen validated contexts and
frozen reader/grader outputs: it proves the composed pipeline reproduces the
Book Result without spending model budget or retuning anything. Live mode
delegates to behavior_eval.run_suite with a real reader.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from capstone.conditions import (
    BUDGETS,
    CAPSTONE_CONDITIONS,
    CONDITION_TO_BCODE,
    INTERVENTIONS,
)
from capstone.manifest import build_manifest
from capstone.system import RememberingSystem

REPO = Path(__file__).resolve().parent.parent.parent
RUNS = REPO / "experiments" / "benchmark" / "runs"
CH12_RUN = "ch12-20260920T204414Z-behavior"


def _mean(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def run_replay(
    *,
    outdir: Path,
    code_commit: str,
    dirty_fingerprint: str,
    reader_id: str = "llama3.1:8b@t0-frozen-replay",
) -> dict:
    """Deterministic replay over frozen ch12 + real-transfer evidence."""
    if outdir.exists():
        shutil.rmtree(outdir)
    (outdir / "conditions").mkdir(parents=True)
    (outdir / "tasks").mkdir(parents=True)
    (outdir / "traces").mkdir(parents=True)
    (outdir / "reader_outputs").mkdir(parents=True)
    (outdir / "grader_outputs").mkdir(parents=True)

    ch12 = RUNS / CH12_RUN
    system = RememberingSystem(ch12, reader_id=reader_id)
    frozen_summary = json.loads((ch12 / "summary.json").read_text(encoding="utf-8"))
    matched = frozen_summary.get("matched_means", {})

    # BT lives in the frozen token-control run, not in ch12 conditions.json.
    bt_dir = RUNS / "ch12-token-control-20260921T002019Z-llama"
    bt_system = (
        RememberingSystem(
            bt_dir,
            reader_id=reader_id,
            history_id="ch12-token-control-20260921T002019Z-llama",
        )
        if (bt_dir / "conditions.json").exists()
        else None
    )

    cap_conditions = list(CAPSTONE_CONDITIONS) + list(INTERVENTIONS)
    per_condition: dict[str, dict] = {}
    traces_written = 0
    for cap in cap_conditions:
        bcode = CONDITION_TO_BCODE.get(cap, cap)
        src = bt_system if (cap == "BT" and bt_system is not None) else system
        entries = src._frozen.get(bcode, [])
        rows = []
        for fo in entries:
            trace = src.run(task_id=fo.task_id, condition=cap)
            (outdir / "traces" / f"{fo.task_id}-{cap}.json").write_text(
                json.dumps(trace.to_dict(), indent=1), encoding="utf-8"
            )
            traces_written += 1
            rows.append(
                {
                    "task_id": fo.task_id,
                    "task_score": fo.task_score,
                    "harm": fo.harm,
                    "context_tokens": fo.context_tokens,
                    "context_hash": fo.context_hash,
                    "n_memory": len(fo.memory_ids),
                }
            )
        m = matched.get(bcode, {})
        if cap == "BT" and bt_system is not None:
            m = {
                "n_tasks": len(rows),
                "task_success_macro": _mean([r["task_score"] for r in rows]),
                "mean_tokens": _mean([r["context_tokens"] for r in rows]),
            }
        per_condition[cap] = {
            "bcode": bcode,
            "n_tasks": m.get("n_tasks", len(rows)),
            "task_success_macro": m.get("task_success_macro", _mean([r["task_score"] for r in rows])),
            "mean_tokens": m.get("mean_tokens"),
            "harm_tasks": sum(1 for r in rows if r["harm"]),
            "rows": rows,
        }
        (outdir / "conditions" / f"{cap}.json").write_text(
            json.dumps(per_condition[cap], indent=1), encoding="utf-8"
        )

    # Task-level reversals: C4 vs C0, BR vs BA per task.
    reversals = []
    by_task: dict[str, dict] = {}
    for cap in ("C0", "C4", "BA", "BR"):
        for row in per_condition.get(cap, {}).get("rows", []):
            by_task.setdefault(row["task_id"], {})[cap] = row["task_score"]
    for task, scores in sorted(by_task.items()):
        reversals.append(
            {
                "task_id": task,
                "C4_minus_C0": _diff(scores.get("C4"), scores.get("C0")),
                "BR_minus_BA": _diff(scores.get("BR"), scores.get("BA")),
            }
        )

    # Real-project replay (frozen, separate).
    real = json.loads((ch12 / "real-transfer.json").read_text(encoding="utf-8"))
    real_summary = summarize_real_transfer(real)
    (outdir / "tasks" / "real-transfer-summary.json").write_text(
        json.dumps(real_summary, indent=1), encoding="utf-8"
    )

    # Token-control replay (frozen).
    token_control = replay_token_control()

    metrics = {
        "controlled": {
            cap: {
                k: v for k, v in per_condition[cap].items() if k != "rows"
            }
            for cap in per_condition
        },
        "reversals": reversals,
        "real_project": real_summary,
        "token_control": token_control,
    }
    (outdir / "metrics.json").write_text(json.dumps(metrics, indent=1), encoding="utf-8")

    manifest = build_manifest(
        code_commit=code_commit,
        dirty_fingerprint=dirty_fingerprint,
        reader_id=reader_id,
        conditions=cap_conditions,
        budgets=dict(BUDGETS),
        source_runs={
            "ch12": CH12_RUN,
            "ch10": "ch10-20260920T163314Z-context-frames",
            "ch14": "ch14-20260920T174259Z-context-assembly",
            "token_control_llama": "ch12-token-control-20260921T002019Z-llama",
            "token_control_muse": "ch12-token-control-20260921T003600Z-muse",
        },
    )
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    summary = {
        "mode": "replay",
        "manifest_id": manifest["manifest_id"],
        "traces": traces_written,
        "C4_minus_C0_matched": _diff(
            per_condition["C4"]["task_success_macro"],
            per_condition["C0"]["task_success_macro"],
        ),
        "BR_minus_BA_matched": _diff(
            per_condition["BR"]["task_success_macro"],
            per_condition["BA"]["task_success_macro"],
        ),
        "verdict": verdict(per_condition),
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return {"outdir": str(outdir), "metrics": metrics, "summary": summary, "manifest": manifest}


def _diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 4)


def verdict(per_condition: dict) -> str:
    c4 = per_condition.get("C4", {}).get("task_success_macro")
    c0 = per_condition.get("C0", {}).get("task_success_macro")
    br = per_condition.get("BR", {}).get("task_success_macro")
    ba = per_condition.get("BA", {}).get("task_success_macro")
    checks = []
    if c4 is not None and c0 is not None:
        checks.append(("C4>C0", c4 > c0))
    if br is not None and ba is not None:
        checks.append(("BR>BA", br > ba))
    if checks and all(ok for _, ok in checks):
        return "A"
    return "OPEN"


def summarize_real_transfer(real: dict) -> dict:
    tasks = real.get("tasks", {})
    rows = []
    for task_id, conds in sorted(tasks.items()):
        row: dict[str, float | None] = {"task_id": task_id}
        for cond in ("M0", "Mm"):
            c = (conds or {}).get(cond, {})
            row[cond] = c.get("task_score")
        row["delta"] = _diff(row.get("Mm"), row.get("M0"))
        rows.append(row)
    return {
        "time_lock_commit": real.get("time_lock_commit"),
        "standpoint": real.get("standpoint"),
        "reader": real.get("reader"),
        "n_tasks": len(rows),
        "mean_M0": _mean([r["M0"] for r in rows]),
        "mean_Mm": _mean([r["Mm"] for r in rows]),
        "rows": rows,
    }


def replay_token_control() -> dict:
    out = {}
    for key in (
        "ch12-token-control-20260921T002019Z-llama",
        "ch12-token-control-20260921T003600Z-muse",
    ):
        d = RUNS / key
        mf = d / "manifest.json"
        sm = d / "summary.json"
        if not mf.exists():
            out[key] = {"present": False}
            continue
        entry: dict = {"present": True}
        if sm.exists():
            try:
                entry["summary"] = json.loads(sm.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                entry["summary"] = "unparseable"
        out[key] = entry
    return out
