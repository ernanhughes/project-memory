"""Frozen-run manifest (H1 pipeline stage 5).

Records corpus version, seed, generator commit, query-set version, and a
sha256 per frozen file. Any change to a frozen variable creates a new run
rather than silently replacing the old result (benchmark-v0.1 section 6).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Manifest:
    corpus_version: str
    seed: int
    n_parametric_worlds: int
    generator_commit: str
    query_set_version: str
    files: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "corpus_version": self.corpus_version,
            "seed": self.seed,
            "n_parametric_worlds": self.n_parametric_worlds,
            "generator_commit": self.generator_commit,
            "query_set_version": self.query_set_version,
            "files": self.files,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generator_commit(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def collect_files(root: Path) -> list[dict]:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            entries.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    return entries


def write_manifest(root: Path, manifest: Manifest) -> Path:
    manifest.files = collect_files(root)
    target = root / "manifest.json"
    target.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8")
    return target


def verify_manifest(root: Path) -> list[str]:
    """Recompute checksums; return list of problems (empty = clean)."""
    problems = []
    try:
        data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"manifest unreadable: {exc}"]
    seen = set()
    for entry in data.get("files", []):
        path = root / entry["path"]
        seen.add(entry["path"])
        if not path.is_file():
            problems.append(f"missing file: {entry['path']}")
            continue
        if sha256_file(path) != entry["sha256"]:
            problems.append(f"checksum mismatch: {entry['path']}")
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    for extra in sorted(actual - seen):
        problems.append(f"unmanifested file: {extra}")
    return problems
