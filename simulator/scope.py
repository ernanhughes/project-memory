"""C4 project-scoped memory: scope attribution filtering (next5 sequence).

The mechanism owns exactly one idea: units attributed to a foreign
project do not enter context for this task's project. Attribution
rides view project tags (system state: ledger renders default to the
task project; constructed foreign views carry theirs explicitly). The
filter reads tags, never text: it must NOT solve anything else.

* same-project stale evidence: passes through (C3 owns temporal).
* same-project poison: passes through (C6 owns trust).
* same-project revoked content: passes through (no revocation
  representation exists; revocation is not temporal expiry).
* untagged views: default to the task project (v0.1 renders carry
  no scope tag by construction).

Pre-registered expectations on the frozen 11-task family: WX
explicit-scope views excluded everywhere they appear; full-history
contexts unchanged (v0.1 history is single-project, so C4 behavioral
equals C1 — no damage by construction, verified live); WXm
metadata-only views excluded where present. Whether exclusion
repairs behavior is measured, not assumed.
"""

from __future__ import annotations


def scope_filter(views: list[dict], task_project: str) -> list[dict]:
    """Keep units attributed to the task project, preserve order."""
    return [v for v in views
            if v.get("project", task_project) == task_project]
