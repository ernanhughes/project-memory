"""Deterministic rule-based actors (T1/T2 ladder).

Systems under test (NullActor, LexicalActor) receive only artifact
views (display_id, kind, date, title, body) plus the task packet —
never ledger records. Evaluator-side probes (OracleActor,
SupersededActor, PreferenceActor) take the hidden world explicitly:
they simulate ceilings and specific memory influences, not deployable
systems. No actor sees expected answers.
"""

from __future__ import annotations

import re

from generator.queries import content_words

from .world import parse_preference_losing

_NEW_RE = re.compile(r"should target ([^.]+)\.")
_OLD_RE = re.compile(r"Use ([^.]+?) for ")
_PREF_RE = re.compile(r"[Pp]refers? ([^.]+?) for ")


def artifact_view(artifact) -> dict:
    return {"display_id": artifact.display_id, "kind": artifact.kind,
            "date": artifact.date, "title": artifact.title,
            "body": artifact.body}


def _overlap(query: str, body: str) -> int:
    return len(set(content_words(query)) & set(content_words(body)))


class NullActor:
    name = "null"

    def act(self, artifacts: list[dict], task) -> dict:
        return {"target": "unknown"}


class OracleActor:
    """Evaluator-side ceiling: proposes the ledger-current target."""

    name = "oracle"

    def __init__(self, world) -> None:
        self.world = world

    def act(self, artifacts: list[dict], task) -> dict:
        target = self.world.current_target(task.topic)
        return {"target": target or "unknown"}


class LexicalActor:
    """Unsafe baseline: top artifact by word overlap decides; first
    target pattern in rank order wins, whatever its source."""

    name = "lexical"

    def act(self, artifacts: list[dict], task) -> dict:
        ranked = sorted(artifacts,
                        key=lambda a: (-_overlap(task.text, a["title"]
                                                 + " " + a["body"]),
                                       a["display_id"]))
        for art in ranked:
            body = art["body"]
            for pattern in (_NEW_RE, _OLD_RE, _PREF_RE):
                match = pattern.search(body)
                if match:
                    return {"target": match.group(1).strip(),
                            "cited": art["display_id"]}
        return {"target": "unknown"}


class SupersededActor:
    """Intervention probe: proposes the latest superseded target,
    simulating stale-memory influence."""

    name = "superseded"

    def __init__(self, world) -> None:
        self.world = world

    def act(self, artifacts: list[dict], task) -> dict:
        targets = self.world.superseded_targets(task.topic)
        return {"target": targets[-1] if targets else "unknown"}


class PreferenceActor:
    """Intervention probe: acts on the losing preference, simulating
    low-authority influence."""

    name = "preference"

    def __init__(self, world) -> None:
        self.world = world

    def act(self, artifacts: list[dict], task) -> dict:
        for record in self.world.ledger.records:
            if (record.topic == task.topic and record.kind == "preference"
                    and record.date <= self.world.as_of):
                parsed = parse_preference_losing(record.content)
                if parsed:
                    return {"target": parsed}
        return {"target": "unknown"}


ACTORS = {
    "null": NullActor,
    "oracle": OracleActor,
    "lexical": LexicalActor,
    "superseded": SupersededActor,
    "preference": PreferenceActor,
}
