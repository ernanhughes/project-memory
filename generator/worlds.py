"""World construction for the v0.1 controlled corpus (H1: E-03 / E-04).

Ground truth: ``spec/running-examples.md`` on main (Memory repo contract:
``spec/benchmark-v0.1.md`` in the book repo). This module transcribes World A
exactly and builds N parametric worlds from the SAME scenario template
builders. World A is not special-cased: it calls the same builders with
fixed canonical parameters, while parametric worlds call them with
seed-generated parameters.

Ledger-template to record-kind mapping (the v0.1 kind set is fixed by the
H1 brief, so the mapping is documented here, not hidden):
- ledger "discussion" that introduces an option  -> kind ``proposal``
- personal stance for a losing option           -> kind ``preference``
- authoritative settlement                      -> kind ``decision``
- observation / benchmark / incident            -> kind ``evidence``
- what currently runs                           -> kind ``production_state``
- echo of a decision                            -> kind ``derived_restatement``

World A display IDs, dates, actors, contents, and edges below are
transcribed from the ledger sections "World A", "Decision and production
state", and "Provenance fixtures". Anything not stated there (e.g. which
render style a decision uses) is chosen by seeded RNG and recorded in
evaluator-side build metadata, never in rendered content.
"""

from __future__ import annotations

import random

from .schema import Ledger, Record

# Numeric suffixes already spent anywhere in the ledger (Worlds A-D plus the
# retired session-022), so parametric display IDs can never collide with
# them. Source: spec/running-examples.md, World A timeline (3, 1, 301, 41,
# 14, 202, 19, 203, 21, 204, 31, 33, 7, 205, 110, 112, 51, 401, 102, 101,
# 302, 103, 40, 44, 9, 206, 6, 207, 109, 117, 118, 120, 24, 72, 201),
# retired session-022 (22), World B (13, 88, 89, 4, 122, 12),
# World C (26, 105, 104, 124, 123, 61, 125, 18, 106, 34),
# World D (128, 129, 127, 126, 107, 108, 121).
RESERVED_SUFFIXES = frozenset(
    {
        1, 3, 4, 6, 7, 9, 12, 13, 14, 18, 19, 21, 22, 24, 26, 31, 33, 34,
        40, 41, 44, 51, 61, 72, 88, 89, 101, 102, 103, 104, 105, 106, 107,
        108, 109, 110, 112, 117, 118, 120, 121, 122, 123, 124, 125, 126,
        127, 128, 129, 201, 202, 203, 204, 205, 206, 207, 301, 302, 401,
    }
)

# Parametric display-ID suffixes allocate from here upward (documented,
# deterministic, disjoint from every ledger suffix above).
PARAM_SUFFIX_START = 1000


class SuffixAllocator:
    """Hands out globally-unique numeric suffixes for parametric display IDs."""

    def __init__(self) -> None:
        self.used = set(RESERVED_SUFFIXES)
        self._next = PARAM_SUFFIX_START

    def take(self, prefix: str) -> str:
        while self._next in self.used:
            self._next += 1
        suffix = self._next
        self.used.add(suffix)
        self._next += 1
        return f"{prefix}-{suffix}"


# ---------------------------------------------------------------------------
# Scenario template builders (shared by World A and parametric worlds)
# ---------------------------------------------------------------------------

def t_proposal_preference_decision(
    *,
    topic: str,
    winning_option: str,
    losing_option: str,
    proposer: str,
    preferrer: str,
    deciders: tuple[str, ...],
    proposal_date: str,
    preference_date: str,
    decision_date: str,
    proposal_id: str,
    preference_id: str,
    decision_id: str,
    decision_keys: tuple[str, ...] = (),
    decision_style: str = "crisp",
    decision_second_id: str = "",
    decision_artifact_kind: str = "adr",
    decision_content: str | None = None,
) -> list[Record]:
    """The 031/033/adr-007 trap shape: proposal, losing preference, decision."""
    return [
        Record(
            key=f"prop-{proposal_id}", kind="proposal", topic=topic,
            content=f"Move {topic} to {winning_option}.",
            scenario="proposal_preference_decision",
            actors=(proposer,), date=proposal_date,
            display_id=proposal_id, artifact_kind="session",
        ),
        Record(
            key=f"pref-{preference_id}", kind="preference", topic=topic,
            content=f"Still prefers {losing_option} for {topic}.",
            scenario="proposal_preference_decision",
            actors=(preferrer,), date=preference_date,
            display_id=preference_id, artifact_kind="session",
        ),
        Record(
            key=f"dec-{decision_id}", kind="decision", topic=topic,
            content=decision_content or f"New {topic} work should target {winning_option}.",
            actors=deciders, date=decision_date, valid_from=decision_date,
            supported_by=decision_keys,
            scenario="proposal_preference_decision",
            display_id=decision_id, artifact_kind=decision_artifact_kind,
            render_style=decision_style,
            second_display_id=decision_second_id,
        ),
    ]


def t_proposal_evidence_rejection(
    *,
    topic: str,
    option: str,
    proposer: str,
    deciders: tuple[str, ...],
    proposal_date: str,
    evidence_date: str,
    decision_date: str,
    evidence_content: str,
    proposal_id: str,
    evidence_id: str,
    decision_id: str,
    decision_style: str = "crisp",
    decision_second_id: str = "",
    decision_artifact_kind: str = "adr",
) -> list[Record]:
    """The Redis shape: proposal, counter-evidence, rejection decision."""
    evidence_key = f"ev-{evidence_id}"
    return [
        Record(
            key=f"prop-{proposal_id}", kind="proposal", topic=topic,
            content=f"Introduce {option} for {topic}.",
            scenario="proposal_evidence_rejection",
            actors=(proposer,), date=proposal_date,
            display_id=proposal_id, artifact_kind="session",
        ),
        Record(
            key=evidence_key, kind="evidence", topic=topic,
            content=evidence_content,
            scenario="proposal_evidence_rejection",
            actors=deciders, date=evidence_date,
            display_id=evidence_id, artifact_kind="session",
        ),
        Record(
            key=f"dec-{decision_id}", kind="decision", topic=topic,
            content=f"Do not introduce {option}.",
            actors=deciders, date=decision_date, valid_from=decision_date,
            supported_by=(evidence_key,),
            scenario="proposal_evidence_rejection",
            display_id=decision_id, artifact_kind=decision_artifact_kind,
            render_style=decision_style,
            second_display_id=decision_second_id,
        ),
    ]


def t_decision_production_split(
    *,
    topic: str,
    old_option: str,
    new_option: str,
    deciders: tuple[str, ...],
    old_decision_date: str,
    new_decision_date: str,
    production_switch_date: str,
    old_decision_id: str,
    new_decision_id: str,
    old_production_id: str,
    new_production_id: str,
    production_start_date: str | None = None,
    old_decision_content: str | None = None,
) -> list[Record]:
    """Decision-vs-production split: what was decided vs what runs."""
    old_dec_key = f"dec-{old_decision_id}"
    new_dec_key = f"dec-{new_decision_id}"
    old_prod_key = f"prod-{old_production_id}"
    new_prod_key = f"prod-{new_production_id}"
    prod_start = production_start_date or old_decision_date
    return [
        Record(
            key=old_dec_key, kind="decision", topic=topic,
            content=old_decision_content or f"Use {old_option} for {topic}.",
            scenario="decision_production_split",
            actors=deciders, date=old_decision_date,
            valid_from=old_decision_date, valid_until=new_decision_date,
            display_id=old_decision_id, artifact_kind="adr",
        ),
        Record(
            key=new_dec_key, kind="decision", topic=topic,
            content=f"New {topic} work should target {new_option}.",
            scenario="decision_production_split",
            actors=deciders, date=new_decision_date,
            valid_from=new_decision_date,
            supersedes=(old_dec_key,),
            display_id=new_decision_id, artifact_kind="adr",
        ),
        Record(
            key=old_prod_key, kind="production_state", topic=topic,
            content=f"{old_option} runs in production.",
            scenario="decision_production_split",
            actors=deciders, date=prod_start,
            valid_from=prod_start, valid_until=production_switch_date,
            display_id=old_production_id, artifact_kind="deployment",
        ),
        Record(
            key=new_prod_key, kind="production_state", topic=topic,
            content=f"{new_option} runs in production.",
            scenario="decision_production_split",
            actors=deciders, date=production_switch_date,
            valid_from=production_switch_date,
            supersedes=(old_prod_key,),
            display_id=new_production_id, artifact_kind="deployment",
        ),
    ]


def t_derived_restatement(
    *,
    topic: str,
    decision_key: str,
    restated_content: str,
    date: str,
    restatement_id: str,
) -> list[Record]:
    """Runbook-echo shape: derived restatement, never independent support."""
    return [
        Record(
            key=f"echo-{restatement_id}", kind="derived_restatement",
            topic=topic, content=restated_content,
            scenario="derived_restatement",
            date=date, derived_from=(decision_key,),
            display_id=restatement_id, artifact_kind="runbook",
        ),
    ]


# ---------------------------------------------------------------------------
# World A: canonical transcription (fixed parameters, shared builders)
# ---------------------------------------------------------------------------

WORLD_A_ACTORS = ("a.silva", "m.okafor", "j.lindqvist")


def build_world_a() -> tuple[list[Record], list[dict]]:
    """World A records plus context-artifact specs.

    Returns (records, context_artifacts). Context artifacts are rendered
    into the fixture for realism (World A "exactly as the ledger defines
    it") but back no ledger record and never appear in an expected-answer
    set in v0.1 scope.
    """
    records: list[Record] = []
    # T2 trap shape with canonical parameters (ledger: 031/033/adr-007).
    records.extend(
        t_proposal_preference_decision(
            topic="event-store backend",
            winning_option="PostgreSQL",
            losing_option="SQLite",
            proposer="a.silva",
            preferrer="j.lindqvist",
            deciders=("m.okafor", "j.lindqvist"),
            proposal_date="2024-07-08",
            preference_date="2024-07-09",
            decision_date="2024-07-11",
            proposal_id="session-031",
            preference_id="session-033",
            decision_id="adr-007",
            decision_keys=("evt-202", "evt-203", "evt-204"),
            decision_content="New event-store work should target PostgreSQL.",
        )
    )
    # Canonical evidence chain supporting evt-205 (ledger provenance table).
    records.extend(
        [
            Record(
                key="evt-202", kind="evidence", topic="event-store backend",
                content="Concurrent-write contention observed under the target workload.",
                scenario="proposal_preference_decision",
                date="2024-06-14", display_id="session-014",
                artifact_kind="session",
            ),
            Record(
                key="evt-203", kind="evidence", topic="event-store backend",
                content="A controlled benchmark confirms the contention problem.",
                scenario="proposal_preference_decision",
                date="2024-06-19", display_id="session-019",
                artifact_kind="session",
            ),
            Record(
                key="evt-204", kind="evidence", topic="event-store backend",
                content="A concurrent importer run fails because of SQLite write contention.",
                scenario="proposal_preference_decision",
                date="2024-06-24", display_id="incident-021",
                artifact_kind="session",
            ),
        ]
    )
    # Rename template-generated keys to the canonical evt-2xx allocation.
    records = _rename_world_a_decision(records)
    # T3 Redis shape with canonical parameters (ledger: 040/044/adr-009).
    records.extend(
        t_proposal_evidence_rejection(
            topic="lookup-latency caching",
            option="Redis",
            proposer="a.silva",
            deciders=("m.okafor", "j.lindqvist"),
            proposal_date="2024-08-05",
            evidence_date="2024-08-08",
            decision_date="2024-08-12",
            evidence_content="The working set fits in memory; Redis is unnecessary.",
            proposal_id="session-040",
            evidence_id="session-044",
            decision_id="adr-009",
        )
    )
    # Rename Redis template keys to canonical allocation (ledger has no
    # evt numbers for 040/044/009; keep template keys, they are unique).
    # T4 decision/production split with canonical parameters.
    records.extend(
        t_decision_production_split(
            topic="event-store backend",
            old_option="SQLite",
            new_option="PostgreSQL",
            deciders=("m.okafor", "j.lindqvist"),
            old_decision_date="2024-03-01",
            new_decision_date="2024-07-11",
            production_switch_date="2024-07-22",
            production_start_date="2024-03-04",
            old_decision_id="adr-003",
            new_decision_id="adr-007",
            old_production_id="deployment-001",
            new_production_id="deployment-101",
            old_decision_content="Use SQLite for the first production event store.",
        )
    )
    # Merge the duplicate adr-007 decision record from T2 and T4: keep the
    # T2 one (carries supported_by), drop the T4 stent. Done below.
    records = _dedupe_adr007(records)
    # Rename remaining template keys to canonical evt/fact allocation.
    records = _rename_world_a_canonical(records)
    # T5 runbook echo with canonical parameters.
    records.extend(
        t_derived_restatement(
            topic="event-store backend",
            decision_key="evt-205",
            restated_content="Operators should use PostgreSQL for the event store.",
            date="2024-08-16",
            restatement_id="runbook-006",
        )
    )
    records = _rename_world_a_canonical(records)

    context = _world_a_context_artifacts()
    return records, context


def _rename_world_a_decision(records: list[Record]) -> list[Record]:
    out = []
    for r in records:
        if r.key == "dec-adr-007":
            # evt-205 supersedes evt-201 (ledger decision yaml); the edge
            # target is rewritten to evt-201 by _rename_world_a_canonical.
            out.append(
                _replace(
                    r, key="evt-205", display_id="adr-007",
                    supersedes=("dec-adr-003",),
                )
            )
        else:
            out.append(r)
    return out


def _dedupe_adr007(records: list[Record]) -> list[Record]:
    """T2 and T4 each emit an adr-007 decision; keep the supported one."""
    seen_evt205 = False
    out = []
    for r in records:
        if r.display_id == "adr-007" and r.kind == "decision":
            if r.key == "evt-205":
                out.append(r)
                seen_evt205 = True
            # drop the T4 duplicate (same content, no support edges)
            continue
        out.append(r)
    assert seen_evt205, "evt-205 missing after dedupe"
    return out


def _rename_world_a_canonical(records: list[Record]) -> list[Record]:
    mapping = {
        "dec-adr-003": "evt-201",
        "prod-deployment-001": "fact-301",
        "prod-deployment-101": "fact-302",
        "echo-runbook-006": "evt-207",
    }
    # Rewrite record keys and all edges to the canonical allocation.
    rename = mapping
    out = []
    for r in records:
        new_key = rename.get(r.key, r.key)
        r2 = _replace(
            r,
            key=new_key,
            supersedes=tuple(rename.get(x, x) for x in r.supersedes),
            supported_by=tuple(rename.get(x, x) for x in r.supported_by),
            derived_from=tuple(rename.get(x, x) for x in r.derived_from),
        )
        out.append(r2)
    return out


def _replace(record: Record, **changes) -> Record:
    data = {f: getattr(record, f) for f in record.__dataclass_fields__}
    data.update(changes)
    return Record(**data)


def _world_a_context_artifacts() -> list[dict]:
    """Artifacts rendered for fixture realism; back no record; never in an
    expected set. Bodies paraphrase the ledger timeline without stating new
    decisions (which would corrupt Q2 expected answers)."""
    return [
        {
            "display_id": "issue-041", "kind": "issue", "date": "2024-05-06",
            "title": "SQLite performance tuning",
            "body": "Open tuning work on SQLite write contention. No decision recorded here.",
        },
        {
            "display_id": "commit-110", "kind": "commit", "date": "2024-07-15",
            "title": "Enable compatibility mode on migration branch",
            "body": "Compatibility mode enabled on the migration branch and in staging before schema changes.",
        },
        {
            "display_id": "commit-112", "kind": "commit", "date": "2024-07-15",
            "title": "Move application writes to PostgreSQL on migration branch",
            "body": "On the migration branch, application writes change to PostgreSQL and are exercised in staging. Production still runs SQLite.",
        },
        {
            "display_id": "session-051", "kind": "session", "date": "2024-07-17",
            "title": "Importer green; backups outstanding",
            "body": "Importer is green on PostgreSQL. Backups still target SQLite and must move before release. No release happened yet.",
        },
        {
            "display_id": "validation-102", "kind": "commit", "date": "2024-07-19",
            "title": "Staging shadow reads agree",
            "body": "Staging shadow reads from SQLite and PostgreSQL agree; migration cleared for production.",
        },
        {
            "display_id": "migration-run-103", "kind": "commit", "date": "2024-07-22",
            "title": "Production migration run",
            "body": "Production migration run completed after compatibility mode, write-path change, shadow reads, and validation.",
        },
        {
            "display_id": "fixture-scan-109", "kind": "commit", "date": "2024-07-23",
            "title": "Fixture scan notes SQLite assumptions",
            "body": "Scan notes benchmark fixtures still encode SQLite timing and locking assumptions. Review needed; nothing decided here.",
        },
        {
            "display_id": "commit-117", "kind": "commit", "date": "2024-08-21",
            "title": "refresh deploy docs",
            "body": "Documentation refresh. No link back to earlier obligations in the message.",
        },
        {
            "display_id": "commit-118", "kind": "commit", "date": "2024-08-27",
            "title": "Move backup configuration to PostgreSQL",
            "body": "Backup configuration and restore check move to PostgreSQL.",
        },
        {
            "display_id": "commit-120", "kind": "commit", "date": "2024-09-03",
            "title": "PostgreSQL-aware benchmark fixtures",
            "body": "Benchmark fixtures updated to PostgreSQL-aware assumptions.",
        },
        {
            "display_id": "release-024", "kind": "deployment", "date": "2024-08-30",
            "title": "First post-migration product release",
            "body": "First product release after the migration ships.",
        },
        {
            "display_id": "session-072", "kind": "session", "date": "2024-10-07",
            "title": "New-service discussion assumes PostgreSQL",
            "body": "New-service discussion proceeds assuming PostgreSQL for event storage.",
        },
    ]


# ---------------------------------------------------------------------------
# Parametric worlds (same builders, generated parameters)
# ---------------------------------------------------------------------------

TOPIC_POOL = [
    ("message-queue backend", "Redpanda", "Kafka"),
    ("full-text search index", "Typesense", "Elasticsearch"),
    ("session cache", "Memcached", "Redis"),
    ("rate limiter", "token bucket", "fixed window"),
    ("blob storage", "S3", "local disk"),
    ("metrics pipeline", "OTLP", "StatsD"),
    ("feature flags", "LaunchDarkly", "config file"),
    ("email delivery", "Postmark", "SendGrid"),
    ("audit log", "append-only store", "rotating files"),
    ("notification fan-out", "SNS", "in-process queue"),
    ("schema registry", "Confluent", "hand-rolled"),
    ("API gateway", "Envoy", "nginx"),
    ("tracing backend", "Tempo", "Jaeger"),
    ("secret store", "Vault", "environment files"),
]

ACTOR_POOL = [
    "t.nguyen", "p.garcia", "s.kim", "d.mbeki",
    "l.fischer", "e.dubois", "k.tanaka", "n.patel",
]

TEMPLATE_NAMES = (
    "discussion_decision",
    "proposal_preference_decision",
    "proposal_evidence_rejection",
    "decision_production_split",
    "derived_restatement",
)


def build_parametric_worlds(
    n: int, alloc: SuffixAllocator, rng: random.Random
) -> list[Record]:
    """Build N parametric worlds cycling through all five templates.

    Every template is used at least twice when n >= 10 (default 12), so
    ablations and audits see each shape repeatedly with different topics,
    actors, dates, and wording seeds.
    """
    if n > len(TOPIC_POOL):
        raise ValueError(f"need {n} distinct topics, pool has {len(TOPIC_POOL)}")
    topics = rng.sample(TOPIC_POOL, n)
    records: list[Record] = []
    base_year, base_month = 2025, 1
    # Decision render styles cycle (seeded offset) so crisp/buried/split
    # are all exercised; pure rng.choice could starve a style by chance.
    style_cycle = ["crisp", "buried", "split"]
    style_pos = rng.randrange(len(style_cycle))

    def next_style() -> str:
        nonlocal style_pos
        style = style_cycle[style_pos % len(style_cycle)]
        style_pos += 1
        return style

    def decision_ids(style: str) -> tuple[str, str, str]:
        """Allocate display IDs for a parametric decision per render style.

        crisp -> ADR id; buried -> session id; split -> two session ids.
        Returns (primary_id, artifact_kind, second_id)."""
        if style == "crisp":
            return alloc.take("adr"), "adr", ""
        if style == "buried":
            return alloc.take("session"), "session", ""
        first, second = alloc.take("session"), alloc.take("session")
        return first, "session", second
    for i in range(n):
        template = TEMPLATE_NAMES[i % len(TEMPLATE_NAMES)]
        topic, opt_new, opt_old = topics[i]
        actors = tuple(rng.sample(ACTOR_POOL, 3))
        month = base_month + (i // 2)
        year = base_year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        d = lambda day: f"{year}-{month:02d}-{day:02d}"
        if template == "discussion_decision":
            style = next_style()
            dec_id, dec_kind, second = decision_ids(style)
            records.extend(
                [
                    Record(
                        key=f"w{i}-prop", kind="proposal", topic=f"{topic}",
                        content=f"Move {topic} to {opt_new}.",
                        scenario="discussion_decision",
                        actors=(actors[0],), date=d(3),
                        display_id=alloc.take("session"), artifact_kind="session",
                    ),
                    Record(
                        key=f"w{i}-dec", kind="decision", topic=f"{topic}",
                        content=f"New {topic} work should target {opt_new}.",
                        scenario="discussion_decision",
                        actors=(actors[1], actors[2]), date=d(10),
                        valid_from=d(10), supported_by=(f"w{i}-prop",),
                        display_id=dec_id, artifact_kind=dec_kind,
                        render_style=style, second_display_id=second,
                    ),
                ]
            )
        elif template == "proposal_preference_decision":
            style = next_style()
            dec_id, dec_kind, second = decision_ids(style)
            records.extend(
                t_proposal_preference_decision(
                    topic=topic, winning_option=opt_new,
                    losing_option=opt_old, proposer=actors[0],
                    preferrer=actors[1], deciders=(actors[1], actors[2]),
                    proposal_date=d(3), preference_date=d(4),
                    decision_date=d(10),
                    proposal_id=alloc.take("session"),
                    preference_id=alloc.take("session"),
                    decision_id=dec_id,
                    decision_artifact_kind=dec_kind,
                    decision_style=style, decision_second_id=second,
                )
            )
        elif template == "proposal_evidence_rejection":
            style = next_style()
            dec_id, dec_kind, second = decision_ids(style)
            records.extend(
                t_proposal_evidence_rejection(
                    topic=topic, option=opt_new, proposer=actors[0],
                    deciders=(actors[1], actors[2]),
                    proposal_date=d(3), evidence_date=d(6),
                    decision_date=d(10),
                    evidence_content=f"Measured evidence shows {opt_new} is unnecessary for {topic}.",
                    proposal_id=alloc.take("session"),
                    evidence_id=alloc.take("session"),
                    decision_id=dec_id,
                    decision_artifact_kind=dec_kind,
                    decision_style=style, decision_second_id=second,
                )
            )
        elif template == "decision_production_split":
            records.extend(
                t_decision_production_split(
                    topic=topic, old_option=opt_old, new_option=opt_new,
                    deciders=(actors[1], actors[2]),
                    old_decision_date=d(1), new_decision_date=d(10),
                    production_switch_date=d(17),
                    old_decision_id=alloc.take("adr"),
                    new_decision_id=alloc.take("adr"),
                    old_production_id=alloc.take("deployment"),
                    new_production_id=alloc.take("deployment"),
                )
            )
        else:  # derived_restatement needs a decision in the same world
            dec_id = alloc.take("adr")
            records.extend(
                [
                    Record(
                        key=f"w{i}-dec", kind="decision", topic=f"{topic}",
                        content=f"New {topic} work should target {opt_new}.",
                        scenario="derived_restatement",
                        actors=(actors[1], actors[2]), date=d(10),
                        valid_from=d(10),
                        display_id=dec_id, artifact_kind="adr",
                    ),
                ]
            )
            records.extend(
                t_derived_restatement(
                    topic=topic, decision_key=f"w{i}-dec",
                    restated_content=f"Operators should use {opt_new} for {topic}.",
                    date=d(20), restatement_id=alloc.take("runbook"),
                )
            )
    return records


def build_ledger(n_parametric: int, seed: int) -> tuple[Ledger, list[dict], SuffixAllocator]:
    """Full hidden ledger: World A + N parametric worlds. Deterministic."""
    rng = random.Random(seed)
    alloc = SuffixAllocator()
    world_a_records, context = build_world_a()
    # Reserve World A suffixes explicitly (allocator preload covers the
    # whole ledger file, but assert World A itself complies).
    for r in world_a_records:
        if r.display_id:
            suffix = int(r.display_id.rsplit("-", 1)[1])
            assert suffix in alloc.used, f"World A suffix not reserved: {r.display_id}"
    records = list(world_a_records)
    records.extend(build_parametric_worlds(n_parametric, alloc, rng))
    ledger = Ledger(records).validate()
    return ledger, context, alloc
