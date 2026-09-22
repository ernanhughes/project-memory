"""Capstone run manifest (contract section 13)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


def build_manifest(
    *,
    code_commit: str,
    dirty_fingerprint: str,
    reader_id: str,
    conditions: list[str],
    budgets: dict,
    source_runs: dict,
    task_set_version: str = "behavior-tasks-v1",
    real_corpus_version: str = "real-transfer-v1@4797720",
) -> dict:
    payload = {
        "experiment": "capstone-integrated-v1",
        "created_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "code_commit": code_commit,
        "dirty_fingerprint": dirty_fingerprint,
        "reader_id": reader_id,
        "grader": "behavior-grader-v2",
        "prompt": "behavior-prompt-v2",
        "task_set_version": task_set_version,
        "real_corpus_version": real_corpus_version,
        "conditions": conditions,
        "budgets": budgets,
        "source_runs": source_runs,
        "decoding": "temperature 0 (frozen replay); live runs record seed",
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()[:16]
    payload["manifest_id"] = digest
    return payload
