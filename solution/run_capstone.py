"""Capstone driver: deterministic replay (default) or live model run.

Replay (no services, no model budget):
    python solution/run_capstone.py --mode replay

Live (requires Ollama reader; frozen grader/prompts):
    python solution/run_capstone.py --mode live --model llama3.1:8b
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "solution"))

from capstone.runner import RUNS, run_replay  # noqa: E402


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO
        ).stdout.strip()
    except OSError:
        return "unknown"


def _dirty() -> str:
    try:
        p = subprocess.run(
            ["git", "status", "--short"], capture_output=True, text=True, cwd=REPO
        ).stdout.strip()
        import hashlib

        return hashlib.sha256(p.encode()).hexdigest()[:16]
    except OSError:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["replay", "live"], default="replay")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--model", default="llama3.1:8b")
    args = ap.parse_args()

    if args.mode == "replay":
        from datetime import datetime, timezone

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        outdir = Path(args.outdir) if args.outdir else RUNS / f"capstone-{stamp}-replay"
        result = run_replay(
            outdir=outdir, code_commit=_commit(), dirty_fingerprint=_dirty()
        )
        print(f"capstone replay -> {result['outdir']}")
        print(f"verdict: {result['summary']['verdict']}")
        print(f"C4-C0: {result['summary']['C4_minus_C0_matched']}  BR-BA: {result['summary']['BR_minus_BA_matched']}")
        return 0

    # Live mode: delegate to the validated ch12 suite (frozen grader/prompts).
    from behavior_eval.experiments import run_suite
    from behavior_eval.runner import ReaderClient

    from_default = RUNS / "capstone-live"
    outdir = Path(args.outdir) if args.outdir else from_default
    outdir.mkdir(parents=True, exist_ok=True)
    client = ReaderClient(model=args.model, live=True)
    suite = run_suite(client, repeats=1, resume=False)
    (outdir / "live-suite.json").__str__()
    import json

    (outdir / "live-suite.json").write_text(json.dumps(suite, indent=1, default=str))
    print(f"capstone live suite -> {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
