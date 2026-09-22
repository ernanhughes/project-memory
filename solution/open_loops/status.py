"""Status resolver: expectation + ordered history -> temporal status.

Closing roles travel inside Chapter 8 event payloads as declarative
pairs — ("open_loops.role", complete|cancel|supersede) plus
("open_loops.target", expectation_id) — so the Chapter 8 log stays the
single canonical history. State-transition satisfaction needs no marker:
a STATE_CHANGED that establishes the desired value closes mechanically.

Closure tiers, strongest first:
1. state-transition — observed desired state (diff/config/state event);
2. explicit — authoritative completion/cancel/supersede marker;
3. semantic — commit text overlapping the opening statement;
4. textual — a "done"-style claim (weakest; never alone over a gap).

Absence discipline: "no completion found" is reported with its search
footprint, never as "no closure happened". History gaps force UNKNOWN.
"""

from __future__ import annotations

import re

from temporal_memory.log import EventLog
from temporal_memory.model import EventEnvelope
from temporal_memory.ordering import parse_ts, temporal_sort

from .config import OpenLoopConfig
from .model import Expectation, SearchFootprint, StatusReport

STATUS = ("OPEN", "SATISFIED", "CANCELLED", "SUPERSEDED", "UNKNOWN")

ROLE_KEY = "open_loops.role"
TARGET_KEY = "open_loops.target"

EXPECTED_CHANNELS = ("sessions", "commits", "diffs", "issues")


def _payload(event: EventEnvelope) -> dict[str, str]:
    return {k: v for k, v in event.payload}


def _tokens(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    normalised = set()
    for word in words:
        # Plural-fold only: generic, no domain vocabulary.
        if len(word) > 3 and word.endswith("s"):
            normalised.add(word[:-1])
        else:
            normalised.add(word)
    return normalised


def token_overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    return len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0


def _channel_of(event: EventEnvelope) -> str:
    source, kind = event.source_id, event.event_type
    # State-changing evidence first: a STATE_CHANGED commit is diff-class
    # evidence (the tier-1 closure channel), not mere commit chatter.
    if kind in ("STATE_CHANGED", "REVISION_MADE", "FACT_ESTABLISHED"):
        return "diffs"
    if source.startswith("session-") or source in ("sessions",):
        return "sessions"
    if source.startswith("issue-") or source in ("issues",):
        return "issues"
    if source.startswith("commit-") or source in ("commits",):
        return "commits"
    if source == "release-svc":
        return "release"
    if source == "decisions":
        return "decisions"
    return "sessions"


def _footprint(expectation: Expectation, log: EventLog,
               valid_at: str, candidates: int,
               current_state_checked: bool) -> SearchFootprint:
    channels = sorted({_channel_of(e) for e in log.events()})
    return SearchFootprint(
        expectation_id=expectation.expectation_id,
        searched_sources=tuple(channels),
        searched_until=valid_at,
        candidate_closures_examined=candidates,
        gaps=tuple(f"{g['source_id']}:{g['expected_seq']}->{g['observed_seq']}"
                   for g in log.gaps()),
        current_state_checked=current_state_checked,
    )


def resolve_status(expectation: Expectation, log: EventLog, valid_at: str,
                   known_at: str | None = None,
                   config: OpenLoopConfig | None = None,
                   texts: dict[str, str] | None = None,
                   current_state_checked: bool = False) -> StatusReport:
    """Compute the expectation's status as of valid_at (known_at bounds
    record time for bitemporal queries). Deterministic; no model calls."""
    config = config or OpenLoopConfig()
    texts = texts or {}
    valid = parse_ts(valid_at)
    known = parse_ts(known_at) if known_at else None

    def visible(event: EventEnvelope) -> bool:
        if valid is not None and parse_ts(event.event_time) is not None \
                and parse_ts(event.event_time) > valid:
            return False
        if known is not None and (parse_ts(event.recorded_at) is None
                                  or parse_ts(event.recorded_at) > known):
            return False
        return True

    ordered = temporal_sort([e for e in log.events() if visible(e)],
                            log.by_id())
    desired = expectation.desired
    opened = parse_ts(expectation.opened_at)
    candidates = 0
    closings: list[tuple[str, str, str]] = []  # (status, event_id, tier)

    for event in ordered:
        event_ts = parse_ts(event.event_time)
        if opened is not None and event_ts is not None and event_ts <= opened:
            continue  # a closing transition must follow the opening
        role = _payload(event).get(ROLE_KEY)
        target = _payload(event).get(TARGET_KEY)
        # Tier 1: observed desired state (mechanical; needs no marker).
        if (event.event_type in ("STATE_CHANGED", "REVISION_MADE",
                                 "FACT_ESTABLISHED")
                and event.subject == desired.subject
                and desired.predicate == "equals"
                and event.value == desired.target):
            candidates += 1
            closings.append(("SATISFIED", event.event_id, "state-transition"))
            continue
        # Tier 2: explicit authoritative markers.
        if target == expectation.expectation_id and role in (
                "complete", "cancel", "supersede"):
            candidates += 1
            mapping = {"complete": ("SATISFIED", "explicit"),
                       "cancel": ("CANCELLED", "explicit"),
                       "supersede": ("SUPERSEDED", "explicit")}
            status, tier = mapping[role]
            closings.append((status, event.event_id, tier))
            continue
        # Tier 3: semantic cross-artifact closure. Only work artifacts
        # (commits/diffs) can close; more mentions cannot close mentions.
        text = texts.get(event.event_id, "")
        channel = _channel_of(event)
        if text and expectation.statement and channel in ("commits", "diffs"):
            candidates += 1
            if token_overlap(text, expectation.statement) >= \
                    config.semantic_overlap_threshold:
                closings.append(("SATISFIED", event.event_id, "semantic"))
                continue
        # Tier 4: textual "done" claim (weakest; work artifacts only).
        if text and channel in ("commits", "diffs") and re.search(
                r"\b(done|completed|finished|implemented|fixed)\b",
                text.lower()):
            candidates += 1
            closings.append(("SATISFIED", event.event_id, "textual"))

    footprint = _footprint(expectation, log, valid_at, candidates,
                           current_state_checked)
    if closings:
        # Earliest valid closing transition in temporal order wins.
        status, closing_id, tier = closings[0]
        detail = f"closed by {closing_id} [{tier}]"
        if len(closings) > 1:
            detail += f"; {len(closings) - 1} later competing close(s) ignored"
        return StatusReport(
            expectation_id=expectation.expectation_id, status=status,
            confidence_class="CLOSED_WITH_EVIDENCE",
            opening_evidence=expectation.opening_evidence,
            closing_evidence=(closing_id,), closure_tier=tier,
            footprint=footprint, detail=detail)

    # No closing transition observed: absence accounting.
    if log.gaps():
        return StatusReport(
            expectation_id=expectation.expectation_id, status="UNKNOWN",
            confidence_class="INCOMPLETE_SEARCH",
            opening_evidence=expectation.opening_evidence,
            footprint=footprint,
            detail="history gap could hide the closure; "
                   "no completion found is not proof of openness")
    covered = [c for c in EXPECTED_CHANNELS
               if c in footprint.searched_sources]
    confidence = ("CORROBORATED_OPEN" if len(covered) == len(EXPECTED_CHANNELS)
                  else "INCOMPLETE_SEARCH")
    deadline_passed = False
    if expectation.required_before:
        trigger = next((e for e in ordered
                        if e.event_id == expectation.required_before), None)
        if trigger is not None:
            deadline_passed = True
        else:
            # A bare timestamp deadline: passed when valid_at reaches it.
            bound = parse_ts(expectation.required_before)
            if bound is not None and valid is not None and valid >= bound:
                deadline_passed = True
    return StatusReport(
        expectation_id=expectation.expectation_id, status="OPEN",
        confidence_class=confidence,
        opening_evidence=expectation.opening_evidence,
        footprint=footprint, deadline_passed=deadline_passed,
        detail=f"no valid closing transition as of {valid_at}; "
               f"searched {footprint.coverage(EXPECTED_CHANNELS)}")
