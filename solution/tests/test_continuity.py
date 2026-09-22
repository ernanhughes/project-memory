"""Continuity guard: retired running-example IDs must stay retired.

Scans reader-facing chapters, concept files, and code fixtures for
tokens the canonical ledger retired or never defined. Files that
document the retirement itself (the audit, repair notes) carry an
explicit allowlist marker.

Run: python -m pytest solution/tests/test_continuity.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Tokens verified retired/absent by planning/continuity-audit.md plus the
# 2026-09-19 repair (session-017 was never canonical; mapped to
# session-033). Audit and repair-note files are exempt (see _EXEMPT).
RETIRED_PATTERNS = [
    r"session-017",
    r"session-022",
    r"session-028",
    r"legacy-event-",
]

# Canonical IDs the rebuilt Chapter 4 depends on; they must exist in the
# ledger-shaped audit (spot check against invented-ID drift).
CHAPTER4_IDS = ["session-031", "session-033", "adr-007"]

_EXEMPT = {
    "planning/continuity-audit.md",  # documents the retired list itself
    "solution/evidence_lineage/fixtures.py",  # documents the repair
    "solution/tests/test_continuity.py",  # this file
}

_SCAN_ROOTS = ["content/books/memory", "solution", "experiments/benchmark"]


def _scan() -> list[str]:
    hits: list[str] = []
    for root in _SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".md", ".txt", ".py", ".json", ".jsonl", ".yaml"}:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in _EXEMPT:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for pattern in RETIRED_PATTERNS:
                if re.search(pattern, text):
                    hits.append(f"{rel}: {pattern}")
    return hits


def test_no_retired_running_example_ids():
    hits = _scan()
    assert hits == [], f"retired IDs reintroduced:\n" + "\n".join(hits)


def test_chapter4_ids_present_in_prose():
    chapter = (REPO_ROOT / "content/books/memory/04-chapter.md").read_text(encoding="utf-8")
    for artifact in CHAPTER4_IDS:
        assert artifact in chapter, f"{artifact} missing from Chapter 4"
