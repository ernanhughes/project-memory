"""Artifact rendering for the v0.1 controlled corpus (H1).

Every record kind has at least three surface realisations; the choice is
seeded and recorded in evaluator-side build metadata, never in content.
Timestamp policy follows the ledger: explicit ISO dates in commits and
deployments; sessions vary (explicit / inconsistent / relative / sometimes
absent); ADRs, issues, and runbooks carry explicit dates.

Bodies never contain ledger-edge terms (supported_by, supersedes,
derived_from, valid_from), oracle/expected-answer vocabulary, other
artifacts' display IDs, or other records' decision statements.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .schema import Record

FORBIDDEN_SUBSTRINGS = (
    "supported_by",
    "derived_from",
    "supersedes",
    "valid_from",
    "valid_until",
    "oracle",
    "expected answer",
    "as_of",
)

PROPOSE_VERBS = ("proposes", "floats the idea", "suggests")
PREFER_VERBS = ("prefers", "leans toward keeping", "would rather keep")
AGREE_VERBS = ("agreed", "resolved", "settled on")


@dataclass
class Artifact:
    display_id: str
    kind: str
    date: str
    title: str
    body: str
    record_keys: tuple[str, ...] = ()
    realisation: str = ""
    has_timestamp: bool = True
    dateline: str = ""  # exact timestamp line embedded in body ("" if none)


def _session_dateline(rng: random.Random, date: str) -> tuple[str, bool]:
    """Seeded timestamp style. Absence is NOT decided here: build.py strips
    datelines from a stratified ~10% per record kind so timestamp presence
    is independent of kind by construction (ledger: sometimes absent)."""
    roll = rng.random()
    if roll < 0.55:
        return f"Date: {date}", True
    if roll < 0.78:
        return f"Date: {date[5:7]}/{date[8:10]}", True  # inconsistent format
    return f"Date: {rng.choice(['earlier this week', 'last Thursday', 'yesterday'])}", True


def _render_session_proposal(rec: Record, rng: random.Random, realisation: str) -> Artifact:
    verb = rng.choice(PROPOSE_VERBS)
    actor = rec.actors[0] if rec.actors else "a team member"
    dateline, has_ts = _session_dateline(rng, rec.date)
    if realisation == "session-direct":
        body = (
            f"{rec.display_id} — working session\n{dateline}\n\n"
            f"{actor} {verb} a change for {rec.topic}: {rec.content}\n"
            "The group notes the idea but reaches no conclusion in this session."
        )
    elif realisation == "session-buried-discussion":
        body = (
            f"{rec.display_id} — working session\n{dateline}\n\n"
            f"Long discussion of quarterly planning, on-call rotations, and {rec.topic}. "
            f"Midway through, {actor} {verb} that {rec.content} "
            "The conversation moves on to release scheduling with nothing settled."
        )
    else:  # session-fragment
        body = (
            f"{rec.display_id} — partial session log\n{dateline}\n\n"
            f"[...]\n{actor}: {rec.content}\n[... log ends ...]"
        )
    return Artifact(rec.display_id, "session", rec.date, f"Session on {rec.topic}",
                    body, (rec.key,), realisation, has_ts, dateline)


def _render_session_preference(rec: Record, rng: random.Random, realisation: str) -> Artifact:
    verb = rng.choice(PREFER_VERBS)
    actor = rec.actors[0] if rec.actors else "a team member"
    dateline, has_ts = _session_dateline(rng, rec.date)
    if realisation == "session-direct":
        body = (
            f"{rec.display_id} — working session\n{dateline}\n\n"
            f"{actor} {verb} the current setup for {rec.topic}: {rec.content}\n"
            "This is a personal stance recorded in discussion."
        )
    elif realisation == "session-buried-discussion":
        body = (
            f"{rec.display_id} — working session\n{dateline}\n\n"
            f"After a long thread about hiring and {rec.topic}, {actor} remarks they "
            f"{verb} things as they are: {rec.content} Others disagree; the topic stays open."
        )
    else:  # session-fragment
        body = (
            f"{rec.display_id} — partial session log\n{dateline}\n\n"
            f"[...]\n{actor}: {rec.content}\n[... log ends ...]"
        )
    return Artifact(rec.display_id, "session", rec.date, f"Session on {rec.topic}",
                    body, (rec.key,), realisation, has_ts, dateline)


def _render_session_evidence(rec: Record, rng: random.Random, realisation: str) -> Artifact:
    dateline, has_ts = _session_dateline(rng, rec.date)
    if realisation == "session-direct":
        body = (
            f"{rec.display_id} — working session\n{dateline}\n\n"
            f"Observation recorded for {rec.topic}: {rec.content}"
        )
    elif realisation == "session-buried-discussion":
        body = (
            f"{rec.display_id} — working session\n{dateline}\n\n"
            f"Mostly routine status updates. Tucked between them, one finding about "
            f"{rec.topic}: {rec.content} The meeting moves on."
        )
    else:  # session-fragment
        body = (
            f"{rec.display_id} — partial session log\n{dateline}\n\n"
            f"[...]\nNote: {rec.content}\n[... log ends ...]"
        )
    return Artifact(rec.display_id, "session", rec.date, f"Session on {rec.topic}",
                    body, (rec.key,), realisation, has_ts, dateline)


def _render_adr_decision(rec: Record, rng: random.Random, realisation: str) -> Artifact:
    parties = ", ".join(rec.actors) if rec.actors else "the team"
    verb = rng.choice(AGREE_VERBS)
    if realisation == "adr-crisp":
        body = (
            f"# {rec.display_id}: {rec.topic}\nDate: {rec.date}\nStatus: accepted\n\n"
            f"Decision: {rec.content}\nDecided by {parties}."
        )
    elif realisation == "adr-narrative":
        body = (
            f"# {rec.display_id}: {rec.topic}\nDate: {rec.date}\n\n"
            f"After weighing the options for {rec.topic}, {parties} {verb} the following: "
            f"{rec.content} Status: accepted."
        )
    else:  # adr-table
        body = (
            f"# {rec.display_id}: {rec.topic}\nDate: {rec.date}\n\n"
            f"| Field | Value |\n|---|---|\n| Decision | {rec.content} |\n"
            f"| Decided by | {parties} |\n| Status | accepted |"
        )
    return Artifact(rec.display_id, "adr", rec.date, f"Decision on {rec.topic}",
                    body, (rec.key,), realisation, True)


def _render_buried_decision(rec: Record, rng: random.Random) -> Artifact:
    verb = rng.choice(AGREE_VERBS)
    parties = ", ".join(rec.actors) if rec.actors else "the team"
    dateline, has_ts = _session_dateline(rng, rec.date)
    body = (
        f"{rec.display_id} — working session\n{dateline}\n\n"
        f"Extended debate about {rec.topic} with no agreement for most of the meeting. "
        f"In the closing minutes, {parties} {verb}: {rec.content}"
    )
    return Artifact(rec.display_id, "session", rec.date,
                    f"Session closing on {rec.topic}",
                    body, (rec.key,), "session-closing-remark", has_ts, dateline)


def _render_split_decision(rec: Record, rng: random.Random) -> tuple[Artifact, Artifact]:
    """Decision content across two artifacts: evidence session + closing."""
    ev_verb = rng.choice(("The numbers show", "The trial run shows", "Measurements confirm"))
    parties = ", ".join(rec.actors) if rec.actors else "the team"
    verb = rng.choice(AGREE_VERBS)
    date_a, has_a = _session_dateline(rng, rec.date)
    date_b, has_b = _session_dateline(rng, rec.date)
    first = Artifact(
        rec.display_id, "session", rec.date, f"Session on {rec.topic}",
        f"{rec.display_id} — working session\n{date_a}\n\n"
        f"{ev_verb} the background for {rec.topic}, and the group asks for a "
        f"follow-up to settle it. Continued in {rec.second_display_id}.",
        (rec.key,), "session-split-a", has_a, date_a,
    )
    second = Artifact(
        rec.second_display_id, "session", rec.date,
        f"Session closing on {rec.topic}",
        f"{rec.second_display_id} — working session\n{date_b}\n\n"
        f"Follow-up to {rec.display_id}. {parties} {verb}: {rec.content}",
        (rec.key,), "session-split-b", has_b, date_b,
    )
    return first, second


def _render_deployment(rec: Record, rng: random.Random, realisation: str) -> Artifact:
    if realisation == "deploy-log":
        body = (
            f"{rec.display_id} — deployment log\nDate: {rec.date}\n\n"
            f"Deployed. Production state for {rec.topic}: {rec.content}"
        )
    elif realisation == "release-note":
        body = (
            f"{rec.display_id} — production note\nDate: {rec.date}\n\n"
            f"Current production state for {rec.topic}: {rec.content}"
        )
    else:  # status-table
        body = (
            f"{rec.display_id} — production status\nDate: {rec.date}\n\n"
            f"| System | State |\n|---|---|\n| {rec.topic} | {rec.content} |"
        )
    return Artifact(rec.display_id, "deployment", rec.date,
                    f"Production state for {rec.topic}",
                    body, (rec.key,), realisation, True)


def _render_runbook(rec: Record, rng: random.Random, realisation: str) -> Artifact:
    if realisation == "runbook-steps":
        body = (
            f"{rec.display_id} — operator runbook\nDate: {rec.date}\n\n"
            f"1. Confirm the current setup for {rec.topic}.\n"
            f"2. {rec.content}\n3. Verify and sign off."
        )
    elif realisation == "runbook-prose":
        body = (
            f"{rec.display_id} — operator runbook\nDate: {rec.date}\n\n"
            f"Operators maintaining {rec.topic} should note: {rec.content}"
        )
    else:  # runbook-commands
        body = (
            f"{rec.display_id} — operator runbook\nDate: {rec.date}\n\n"
            f"    # {rec.topic}\n    # {rec.content}\n    verify --system {rec.topic}"
        )
    return Artifact(rec.display_id, "runbook", rec.date, f"Runbook for {rec.topic}",
                    body, (rec.key,), realisation, True)


def _render_commit(context: dict, rng: random.Random, realisation: str) -> Artifact:
    if realisation == "commit-conventional":
        body = (
            f"{context['display_id']} — commit\nDate: {context['date']}\n\n"
            f"{context['title']}\n\n{context['body']}"
        )
    elif realisation == "commit-terse":
        body = (
            f"{context['display_id']} — commit\nDate: {context['date']}\n\n"
            f"{context['title']}: {context['body']}"
        )
    else:  # commit-verbose
        body = (
            f"{context['display_id']} — commit\nDate: {context['date']}\n\n"
            f"Subject: {context['title']}\n\nRationale: {context['body']}\n"
            "Reviewed on the branch before landing."
        )
    return Artifact(context["display_id"], context["kind"], context["date"],
                    context["title"], body, (), realisation, True)


def _render_issue(context: dict, rng: random.Random, realisation: str) -> Artifact:
    if realisation == "issue-structured":
        body = (
            f"{context['display_id']} — issue\nDate: {context['date']}\n\n"
            f"Title: {context['title']}\nBackground: {context['body']}"
        )
    elif realisation == "issue-freeform":
        body = (
            f"{context['display_id']} — issue\nDate: {context['date']}\n\n"
            f"{context['title']}. {context['body']}"
        )
    else:  # issue-checklist
        body = (
            f"{context['display_id']} — issue\nDate: {context['date']}\n\n"
            f"- [ ] {context['title']}\n  Notes: {context['body']}"
        )
    return Artifact(context["display_id"], context["kind"], context["date"],
                    context["title"], body, (), realisation, True)


def render_record(
    rec: Record, rng: random.Random, realisation: str
) -> list[Artifact]:
    """Render one ledger record to artifact(s). Split decisions yield two."""
    if rec.kind == "proposal":
        return [_render_session_proposal(rec, rng, realisation)]
    if rec.kind == "preference":
        return [_render_session_preference(rec, rng, realisation)]
    if rec.kind == "evidence":
        return [_render_session_evidence(rec, rng, realisation)]
    if rec.kind == "decision":
        if rec.render_style == "crisp":
            return [_render_adr_decision(rec, rng, realisation)]
        if rec.render_style == "buried":
            return [_render_buried_decision(rec, rng)]
        first, second = _render_split_decision(rec, rng)
        return [first, second]
    if rec.kind == "production_state":
        return [_render_deployment(rec, rng, realisation)]
    if rec.kind == "derived_restatement":
        return [_render_runbook(rec, rng, realisation)]
    raise ValueError(f"unknown kind {rec.kind}")


REALISATIONS: dict[str, tuple[str, ...]] = {
    "proposal": ("session-direct", "session-buried-discussion", "session-fragment"),
    "preference": ("session-direct", "session-buried-discussion", "session-fragment"),
    "evidence": ("session-direct", "session-buried-discussion", "session-fragment"),
    "decision": ("adr-crisp", "adr-narrative", "adr-table"),
    "production_state": ("deploy-log", "release-note", "status-table"),
    "derived_restatement": ("runbook-steps", "runbook-prose", "runbook-commands"),
    "commit": ("commit-conventional", "commit-terse", "commit-verbose"),
    "issue": ("issue-structured", "issue-freeform", "issue-checklist"),
}

SESSION_REALISATIONS = REALISATIONS["proposal"]


def choose_realisation(
    rng: random.Random, kind: str, decision_style: str = "crisp"
) -> str:
    """Seeded realisation choice. Buried/split decisions bypass ADR styles."""
    if kind == "decision" and decision_style != "crisp":
        return "n/a-style-carried-by-shape"
    return rng.choice(list(REALISATIONS[kind]))


def render_context_artifact(spec: dict, rng: random.Random) -> Artifact:
    if spec["kind"] == "session":
        realisation = rng.choice(
            ["context-session-plain", "context-session-detailed", "context-session-brief"]
        )
        dateline, has_ts = _session_dateline(rng, spec["date"])
        if realisation == "context-session-brief":
            body = f"{spec['display_id']} — session note\n{dateline}\n\n{spec['body']}"
        else:
            body = (
                f"{spec['display_id']} — working session\n{dateline}\n\n"
                f"{spec['title']}. {spec['body']}"
            )
        return Artifact(spec["display_id"], "session", spec["date"],
                        spec["title"], body, (), realisation, has_ts, dateline)
    if spec["kind"] == "deployment":
        realisation = rng.choice(
            ["context-deploy-log", "context-release-note", "context-status-line"]
        )
        body = (
            f"{spec['display_id']} — production note\nDate: {spec['date']}\n\n"
            f"{spec['title']}. {spec['body']}"
        )
        return Artifact(spec["display_id"], "deployment", spec["date"],
                        spec["title"], body, (), realisation, True)
    realisation = rng.choice(list(REALISATIONS[spec["kind"]]))
    if spec["kind"] == "commit":
        return _render_commit(spec, rng, realisation)
    return _render_issue(spec, rng, realisation)


def check_body_hygiene(artifacts: list[Artifact]) -> list[str]:
    """Bodies must not leak ledger vocabulary. Returns violations."""
    problems = []
    for art in artifacts:
        lowered = art.body.lower()
        for term in FORBIDDEN_SUBSTRINGS:
            if term in lowered:
                problems.append(f"{art.display_id}: contains {term!r}")
    return problems
