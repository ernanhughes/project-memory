"""Shared notebook support utilities for the Memory book companion notebooks.

This module provides presentation helpers, frozen run loading, repository
discovery, and consistent formatting. It does NOT contain memory algorithms
or scoring logic duplicated from the actual packages.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class RepoPaths:
    """Discovered repository paths."""
    root: Path
    solution: Path
    experiments: Path
    content: Path
    metadata: Path
    notebooks: Path

    @classmethod
    def discover(cls, start: Path | None = None) -> "RepoPaths":
        """Find the repository root by looking for known markers."""
        if start is None:
            start = Path.cwd()
        current = start.resolve()
        while current != current.parent:
            if (current / "solution").exists() and (current / "content").exists():
                return cls(
                    root=current,
                    solution=current / "solution",
                    experiments=current / "experiments",
                    content=current / "content",
                    metadata=current / "metadata",
                    notebooks=current / "notebooks" / "memory",
                )
            current = current.parent
        raise RuntimeError("Could not find repository root (no solution/ and content/ directories)")


REPO = RepoPaths.discover()


def load_frozen_run(run_id: str) -> dict[str, Any]:
    """Load a frozen experiment run by its run directory name.

    Args:
        run_id: The run directory name (e.g., "ch12-20260920T204414Z-behavior")

    Returns:
        Dictionary with manifest, summary, conditions, metrics, etc.
    """
    run_dir = REPO.experiments / "benchmark" / "runs" / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Frozen run not found: {run_dir}")

    result = {"run_id": run_id, "path": str(run_dir)}

    for fname in ["manifest.json", "summary.json", "conditions.json", "metrics.json", "real-transfer.json"]:
        fpath = run_dir / fname
        if fpath.exists():
            result[fname.replace(".json", "")] = json.loads(fpath.read_text(encoding="utf-8"))

    # Load condition directories if present
    conditions = {}
    for cond_dir in run_dir.iterdir():
        if cond_dir.is_dir() and (cond_dir / "manifest.json").exists():
            conditions[cond_dir.name] = {
                "manifest": json.loads((cond_dir / "manifest.json").read_text(encoding="utf-8")),
                "config": json.loads((cond_dir / "config.json").read_text(encoding="utf-8")) if (cond_dir / "config.json").exists() else None,
                "cases": [json.loads(line) for line in (cond_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines()] if (cond_dir / "cases.jsonl").exists() else [],
            }
    if conditions:
        result["condition_details"] = conditions

    return result


def load_chapter_metadata(chapter_num: int) -> dict[str, Any]:
    """Load chapter metadata YAML."""
    import yaml
    meta_path = REPO.metadata / f"{chapter_num:02d}-chapter.yaml"
    if not meta_path.exists():
        raise FileNotFoundError(f"Chapter metadata not found: {meta_path}")
    return yaml.safe_load(meta_path.read_text(encoding="utf-8"))


def load_fixtures(fixture_name: str) -> dict[str, Any]:
    """Load a fixture file from solution/fixtures/."""
    fixture_path = REPO.solution / "fixtures" / fixture_name
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def render_orientation_block(
    chapter: int,
    title: str,
    central_question: str,
    main_concepts: list[str],
    implementation_modules: list[str],
    experiment_refs: list[str],
    evidence_status: str,
    depends_on: list[str] | None = None,
) -> str:
    """Generate a Markdown orientation block for a notebook."""
    depends = depends_on or []
    lines = [
        "---",
        f"# Chapter {chapter} — {title}",
        "",
        "## Orientation",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Chapter | {chapter}: {title} |",
        f"| Central question | {central_question} |",
        f"| Main concepts | {', '.join(main_concepts)} |",
        f"| Implementation | {', '.join(implementation_modules)} |",
        f"| Experiment | {', '.join(experiment_refs) if experiment_refs else 'pending'} |",
        f"| Evidence status | {evidence_status} |",
        f"| Depends on | {', '.join(depends) if depends else 'none'} |",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def render_table(data: list[dict], title: str | None = None) -> pd.DataFrame:
    """Render a list of dicts as a pandas DataFrame for nice display."""
    df = pd.DataFrame(data)
    if title:
        print(f"### {title}")
    return df


def render_trace_table(trace: dict, fields: list[str]) -> pd.DataFrame:
    """Extract specific fields from a trace dict for display."""
    return pd.DataFrame([{f: trace.get(f) for f in fields}])


def check_optional_service(service: str) -> bool:
    """Check if an optional service (Ollama, PostgreSQL, etc.) is available."""
    if service == "ollama":
        try:
            import requests
            r = requests.get("http://localhost:11434/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False
    elif service == "postgresql":
        try:
            import psycopg2
            conn = psycopg2.connect(os.environ.get("MEMORY_BASELINE_DSN", "postgresql://postgres:postgres@localhost:5434/memory_baseline"), connect_timeout=2)
            conn.close()
            return True
        except Exception:
            return False
    return False


def get_git_commit() -> str:
    """Get the current git commit hash."""
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO.root, text=True).strip()
    except Exception:
        return "unknown"


def get_dirty_fingerprint() -> str:
    """Get a fingerprint of uncommitted changes."""
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO.root, text=True).strip()
        return "clean" if not status else "dirty"
    except Exception:
        return "unknown"


# Default execution policy: use frozen artifacts by default
RUN_LIVE = False