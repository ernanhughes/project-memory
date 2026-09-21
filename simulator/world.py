"""Deterministic project world state for action tasks (T1).

WorldState answers, from the hidden ledger at an explicit as_of, what
a correct new-service proposal must target and which options are
superseded (choosing one is harmful: acting on superseded operational
state). Target options are parsed from canonical decision phrasing;
topics whose decisions do not parse yield no task rather than a
guessed one.
"""

from __future__ import annotations

import re

from generator.schema import Ledger

_NEW_TARGET_RE = re.compile(r"should target ([^.]+)\.")
_OLD_USE_RE = re.compile(r"Use ([^.]+?) for ")
_PREF_RE = re.compile(r"[Pp]refers? ([^.]+?) for ")


def norm(option: str) -> str:
    return option.strip().casefold()


def parse_new_target(content: str) -> str | None:
    match = _NEW_TARGET_RE.search(content)
    return match.group(1).strip() if match else None


def parse_old_use(content: str) -> str | None:
    match = _OLD_USE_RE.search(content)
    return match.group(1).strip() if match else None


def parse_preference_losing(content: str) -> str | None:
    match = _PREF_RE.search(content)
    return match.group(1).strip() if match else None


class WorldState:
    """Hidden-ledger view at one as_of. Evaluator side only."""

    def __init__(self, ledger: Ledger, as_of: str) -> None:
        self.ledger = ledger
        self.as_of = as_of
        self._by_key = ledger.by_key()

    def decisions(self, topic: str) -> list:
        return [r for r in self.ledger.records
                if r.topic == topic and r.kind == "decision"
                and r.date <= self.as_of]

    def current_target(self, topic: str) -> str | None:
        """Latest currently-valid decision target, or None."""
        cands = [r for r in self.decisions(topic)
                 if (r.valid_from or "") <= self.as_of
                 and (r.valid_until is None or self.as_of < r.valid_until)]
        if not cands:
            return None
        best = max(cands, key=lambda r: (r.date, r.key))
        return parse_new_target(best.content)

    def superseded_targets(self, topic: str) -> list[str]:
        """Targets of decisions no longer current at as_of."""
        out = []
        for r in self.decisions(topic):
            if r.valid_until is not None and r.valid_until <= self.as_of:
                parsed = (parse_new_target(r.content)
                          or parse_old_use(r.content))
                if parsed:
                    out.append(parsed)
        return sorted(set(out))

    def known_options(self, topic: str) -> list[str]:
        opts = []
        current = self.current_target(topic)
        if current:
            opts.append(current)
        opts.extend(self.superseded_targets(topic))
        return sorted(set(opts))

    def production_current(self, topic: str) -> str | None:
        covering = [r for r in self.ledger.records
                    if r.topic == topic and r.kind == "production_state"
                    and (r.valid_from or "") <= self.as_of
                    and (r.valid_until is None
                         or self.as_of < r.valid_until)]
        if not covering:
            return None
        return max(covering, key=lambda r: (r.valid_from or "",
                                            r.key)).content
