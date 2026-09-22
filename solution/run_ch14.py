"""Frozen Chapter 14 benchmark driver: assembly over frozen C5 input.

Usage:
    python solution/run_ch14.py [--outdir ...] [--no-reader]

Selection is frozen at Chapter 10 C5 bundles; only assembly varies.
Every run freezes the manifest (code commit, Ch10/Ch11 source runs,
policy versions, budgets, conditions), per-task metrics by budget,
assembly traces, rendered contexts, the oracle audit, failure
attribution, and the drop-policy backtest.
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

from context_frames import assembly as A  # noqa: E402
from context_frames.assembly_experiments import (  # noqa: E402
    BUDGETS,
    CONDITIONS,
    load_ch10_inputs,
    run_suite,
)

CH10_RUN = "ch10-20260920T163314Z-context-frames"
CH11_RUN = "ch11-20260920T171039Z-derived-loops"


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--budgets", default=None,
                        help="comma-separated subset, e.g. 768,full")
    args = parser.parse_args()

    budgets = BUDGETS
    if args.budgets:
        budgets = tuple(int(b) if b != "full" else "full"
                        for b in args.budgets.split(","))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else (
        ROOT / "experiments" / "benchmark" / "runs"
        / f"ch14-{stamp}-context-assembly")
    outdir.mkdir(parents=True, exist_ok=True)

    inputs = load_ch10_inputs()
    suite = run_suite(budgets=budgets, inputs=inputs)

    (outdir / "results.json").write_text(json.dumps(
        {c: {b: {"mean": suite["conditions"][c][b]["mean"],
                 "tasks": suite["conditions"][c][b]["tasks"]}
              for b in suite["conditions"][c]}
         for c in suite["conditions"]}, indent=2))
    (outdir / "metrics.json").write_text(json.dumps(
        {c: {b: suite["conditions"][c][b]["mean"]
              for b in suite["conditions"][c]}
         for c in suite["conditions"]}, indent=2))
    (outdir / "policy-backtest.json").write_text(
        json.dumps(suite["backtest"], indent=2))

    traces_dir = outdir / "assembly-traces"
    renders_dir = outdir / "rendered-contexts"
    traces_dir.mkdir(exist_ok=True)
    renders_dir.mkdir(exist_ok=True)
    for condition, by_budget in suite["conditions"].items():
        for budget, payload in by_budget.items():
            safe = f"{condition}-budget-{budget}"
            (traces_dir / f"{safe}.json").write_text(json.dumps(
                payload["traces"], indent=2))
            (renders_dir / f"{safe}.json").write_text(json.dumps(
                payload["renders"], indent=2))

    manifest = {
        "suite": suite["suite"],
        "run_id": outdir.name,
        "created_at": stamp,
        "ch10_source_run": CH10_RUN,
        "ch11_source_run": CH11_RUN,
        "selection_input": "C5",
        "assembly_version": suite["assembly_version"],
        "drop_policy_version": suite["drop_policy_version"],
        "render_version": suite["render_version"],
        "token_convention": "estimate_tokens chars//4 "
                            "(counted=text, rendered=+headers/marks)",
        "budgets": [str(b) for b in budgets],
        "conditions": list(suite["conditions"].keys()),
        "code_commit": _commit(),
        "fixture_digest": suite["fixture_digest"],
        "reader": None,
        "note": "evidence-sufficiency headline; reader behaviour "
                "secondary via frozen Ch10 answer coverage",
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"wrote {outdir}")
    for condition in CONDITIONS:
        means = suite["conditions"][condition]
        full = means.get("full", {}).get("mean", {})
        print(f"  {condition:<14} full: req={full.get('required_recall')} "
              f"tok={full.get('counted_tokens')}")
    b = suite["backtest"]
    print(f"  backtest {b['candidate']}: "
          f"tokens {b['base_tokens']}->{b['candidate_tokens']} "
          f"promoted={b['promoted']} breaches={b['breaches']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
