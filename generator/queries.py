"""Q1/Q2 query construction with mechanical expected answers (H1 stage 4).

Every query carries an explicit ``as_of``. Query phrasing comes from a pool
disjoint from ledger content (enforced by the lexical-overlap audit); topic
names necessarily overlap since queries must be about the topic.

Expected answers are derived mechanically from hidden records:

- Q1 (where discussed): supporting artifact display IDs for the topic with
  artifact date on/before as_of. Artifact-level granularity in v0.1; span
  offsets are deferred (recorded as future work in the audit report).
- Q2-decision (what decided / what should new work target): the latest
  decision on the topic with date and valid_from on/before as_of; status is
  "current" when valid_until is None or as_of precedes it, else
  "superseded". Content is the decision's canonical statement.
- Q2-production (what runs in production): the production_state record
  covering as_of, i.e. valid_from <= as_of < (valid_until or +infinity).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .schema import Ledger, Record

STOPWORDS = frozenset(
    "the a an of for to in on about did does do what where which team "
    "current currently runs run running target targets should new code "
    "there their it its and or was were is are be been being".split()
)

Q1_TEMPLATES = (
    "Where did the team discuss {topic}?",
    "In which sessions did {topic} come up?",
    "Find the discussions of {topic}.",
    "Where was {topic} talked about?",
)

Q2_DECISION_TEMPLATES = (
    "What did the team decide about {topic}?",
    "What was decided regarding {topic}?",
    "What should new work target for {topic}?",
)

Q2_PRODUCTION_TEMPLATES = (
    "What runs in production for {topic}?",
    "Which system currently runs {topic} in production?",
)


@dataclass
class Query:
    query_id: str
    family: str  # "Q1" | "Q2-decision" | "Q2-production"
    topic: str
    text: str
    as_of: str


@dataclass
class Expected:
    query_id: str
    family: str
    topic: str
    as_of: str
    answer: dict
    supporting: list[str]


def content_words(text: str) -> list[str]:
    return [
        w.strip(".,?:;!\"'()").lower()
        for w in text.split()
        if w.strip(".,?:;!\"'()").lower() not in STOPWORDS
        and len(w.strip(".,?:;!\"'()")) > 2
    ]


def _records_for_topic(ledger: Ledger, topic: str) -> list[Record]:
    return ledger.by_topic(topic)


def _display_of(rec: Record) -> list[str]:
    out = [rec.display_id] if rec.display_id else []
    if rec.second_display_id:
        out.append(rec.second_display_id)
    return out


def q1_expected(
    ledger: Ledger, artifacts_by_display: dict, topic: str, as_of: str
) -> tuple[dict, list[str]]:
    supporting = sorted(
        {
            did
            for rec in _records_for_topic(ledger, topic)
            for did in _display_of(rec)
            if did in artifacts_by_display
            and artifacts_by_display[did].date <= as_of
        }
    )
    return {"kind": "artifact_set"}, supporting


def q2_decision_expected(
    ledger: Ledger, topic: str, as_of: str
) -> tuple[dict, list[str]]:
    cands = [
        r
        for r in _records_for_topic(ledger, topic)
        if r.kind == "decision" and r.date <= as_of and (r.valid_from or "") <= as_of
    ]
    if not cands:
        return {"decision": None, "status": "no-decision"}, []
    best = max(cands, key=lambda r: (r.date, r.key))
    status = (
        "current"
        if best.valid_until is None or as_of < best.valid_until
        else "superseded"
    )
    supporting = sorted(
        {
            did
            for rec in _records_for_topic(ledger, topic)
            if rec.date <= as_of
            for did in _display_of(rec)
        }
    )
    return (
        {"decision": best.content, "status": status, "decided_at": best.date},
        supporting,
    )


def q2_production_expected(
    ledger: Ledger, topic: str, as_of: str
) -> tuple[dict, list[str]]:
    covering = [
        r
        for r in _records_for_topic(ledger, topic)
        if r.kind == "production_state"
        and (r.valid_from or "") <= as_of
        and (r.valid_until is None or as_of < r.valid_until)
    ]
    if not covering:
        return {"production": None, "status": "unknown"}, []
    best = max(covering, key=lambda r: (r.valid_from or "", r.key))
    supporting = sorted(
        {did for did in _display_of(best) if did}
    )
    return (
        {
            "production": best.content,
            "status": "current",
            "effective_at": best.date,
        },
        supporting,
    )


def build_queries(
    ledger: Ledger,
    artifacts_by_display: dict,
    rng: random.Random,
    as_of_dates: list[str],
) -> tuple[list[Query], list[Expected]]:
    """One Q1 + Q2-decision per decision-bearing topic, Q2-production where
    production_state records exist. as_of values cycle deterministically."""
    topics = sorted({r.topic for r in ledger.records})
    queries: list[Query] = []
    expected: list[Expected] = []
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"q-{counter:06d}"

    for topic in topics:
        recs = _records_for_topic(ledger, topic)
        kinds = {r.kind for r in recs}
        as_of = as_of_dates[counter % len(as_of_dates)]
        qid = next_id()
        text = rng.choice(Q1_TEMPLATES).format(topic=topic)
        queries.append(Query(qid, "Q1", topic, text, as_of))
        answer, supporting = q1_expected(ledger, artifacts_by_display, topic, as_of)
        expected.append(Expected(qid, "Q1", topic, as_of, answer, supporting))
        if "decision" in kinds:
            as_of_d = as_of_dates[counter % len(as_of_dates)]
            qid_d = next_id()
            text_d = rng.choice(Q2_DECISION_TEMPLATES).format(topic=topic)
            queries.append(Query(qid_d, "Q2-decision", topic, text_d, as_of_d))
            answer_d, supporting_d = q2_decision_expected(ledger, topic, as_of_d)
            expected.append(
                Expected(qid_d, "Q2-decision", topic, as_of_d, answer_d, supporting_d)
            )
        if "production_state" in kinds:
            as_of_p = as_of_dates[counter % len(as_of_dates)]
            qid_p = next_id()
            text_p = rng.choice(Q2_PRODUCTION_TEMPLATES).format(topic=topic)
            queries.append(Query(qid_p, "Q2-production", topic, text_p, as_of_p))
            answer_p, supporting_p = q2_production_expected(ledger, topic, as_of_p)
            expected.append(
                Expected(qid_p, "Q2-production", topic, as_of_p, answer_p, supporting_p)
            )
    return queries, expected


def default_as_of_dates() -> list[str]:
    """Explicit cuts exercising pre/post boundaries (decision 07-11,
    production switch 07-22, release 08-30) plus corpus end."""
    return [
        "2024-07-10",
        "2024-07-15",
        "2024-07-22",
        "2024-08-23",
        "2024-12-31",
        "2025-06-30",
    ]
