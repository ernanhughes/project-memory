"""Smoke test for the metadata validator (next9 section 16)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def test_validator_passes() -> None:
    r = subprocess.run(
        [sys.executable, "scripts/validate_metadata.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout
