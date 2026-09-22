"""Baselines: mention-only (M0), mention+nearby-closure (M1),
full-history derivation (M2), and the empty/all-open sanity controls.

M0/M1 work over artifact texts, deliberately plausible: sensible
patterns, deduplication by normalised mention. They are expected to
show recall without precision — measured, not assumed.
"""

from __future__ import annotations

import re

TASK_PATTERNS = (
    r"\btodo\b", r"\bfixme\b", r"\bneed to\b", r"\bneeds to\b",
    r"\bshould\b", r"\bmust\b", r"\bfollow[- ]up\b",
    r"\bbefore release\b", r"\bneed\b",
)
CLOSE_PATTERNS = (
    r"\bcompleted\b", r"\bdone\b", r"\bfixed\b", r"\bimplemented\b",
    r"\bcancelled\b", r"\bcanceled\b", r"\bcomplete\b",
)


def _mentions(texts: dict[str, str]) -> dict[str, list[str]]:
    """event_id -> matched task-like phrases."""
    out: dict[str, list[str]] = {}
    for eid, text in texts.items():
        hits = [p for p in TASK_PATTERNS if re.search(p, text.lower())]
        if hits:
            out[eid] = hits
    return out


def mention_only(texts: dict[str, str]) -> dict[str, str]:
    """M0: task-like mention with no nearby 'done' in the same text."""
    result = {}
    for eid, hits in _mentions(texts).items():
        text = texts[eid].lower()
        if any(re.search(p, text) for p in CLOSE_PATTERNS):
            continue
        result[eid] = "OPEN"
    return result


def mention_nearby_closure(texts: dict[str, str],
                           links: dict[str, list[str]] | None = None,
                           ) -> dict[str, str]:
    """M1: M0 plus closure words in the same or explicitly linked texts."""
    links = links or {}
    result = {}
    for eid in _mentions(texts):
        pool = " ".join([texts[eid]] + [texts.get(other, "")
                                        for other in links.get(eid, [])])
        if any(re.search(p, pool.lower()) for p in CLOSE_PATTERNS):
            result[eid] = "CLOSED"
        else:
            result[eid] = "OPEN"
    return result


def empty_list(_texts: dict[str, str]) -> dict[str, str]:
    """Sanity control: nothing is ever open (trivial precision)."""
    return {}


def all_open(texts: dict[str, str]) -> dict[str, str]:
    """Sanity control: every task-like mention stays open forever."""
    return dict.fromkeys(_mentions(texts), "OPEN")
