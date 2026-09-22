"""Regression: frozen-reader reuse must segregate by reader.

llama and ministral Chapter 12 runs share context strings (hence
hashes) but not outcomes. A (task, hash) lookup without the reader
element silently borrows the wrong reader's row (41 rows in the first
ch13 ministral attempt)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import run_ch13 as R


def _frozen(tmp: Path, run: str, reader: str) -> None:
    d = tmp / run
    d.mkdir()
    (d / "conditions.json").write_text(json.dumps({
        "B3": [{"outcome": {"task_id": "fix-store",
                            "context_hash": "abc123",
                            "task_score": 0.8333 if run == "ch12-llama"
                            else 1.0,
                            "reader": reader}}]}))


def test_reuse_lookup_segregates_readers(tmp_path):
    _frozen(tmp_path, "ch12-llama", "llama3.1:8b@t0")
    _frozen(tmp_path, "ch12-ministral", "ministral-3:8b@t0")
    lookup = R.reuse_lookup(tmp_path / "ch12-llama",
                            tmp_path / "ch12-ministral")
    llama = lookup[("fix-store", "abc123", "llama3.1:8b@t0")]
    mini = lookup[("fix-store", "abc123", "ministral-3:8b@t0")]
    assert llama["outcome"]["reader"] == "llama3.1:8b@t0"
    assert mini["outcome"]["reader"] == "ministral-3:8b@t0"
    assert llama["outcome"]["task_score"] != mini["outcome"]["task_score"]
    assert ("fix-store", "abc123", "muse@t0") not in lookup
