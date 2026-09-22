"""Semantic re-grounding fixtures for Chapter 13 (gate v2).

Each scenario carries a small ledger: graph nodes, reconciliation
records, later events, an as_of date, and the frame subject. The gate
derives establishment hints from this evidence (frame_evidence.py);
it never sees the expected hint or action.

Behavioral ground is shared with the frozen v1 runs BY DESIGN and
recorded explicitly: each scenario points at (source_run,
source_scenario) whose frozen reader rows it recomputes under the new
gate. The unit under test is the DECISION procedure (evidence ->
class -> action -> condition), not the reader. Old canonicals
(ch13-dev-v1, ch13-eval-v1, ch13-eval-v1-ministral) remain historical
and are never mutated; new run dirs carry the ch13s- prefix.

Split rule: SD-* (dev, 12) tunes the mapping; SE-* (eval, 9) is
held out. Both splits cover the six positive-control reconciliation
cases: same_event+current, correspondence_only, stale, conflicting,
invalidated, cross_scope. The anti-promotion invariant (HARD only via
corroborated) is checked by the runner on both splits.

Ledger vocabulary reuses World A display ids (adr-007, session-051,
commit-118, evt-205, fact-301, adr-003, session-014, session-019,
incident-021, runbook-006/009); each scenario builds its own graph so
ids never collide across fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemScenario:
    scenario_id: str
    family: str
    behavior_task: str  # behavior_eval task id
    ch10_task: str | None  # corpus task id; None for derived cleanup
    # Ledger: nodes as (node_id, date, project, valid_until,
    # contradicts, references); recs as (rec_id, a, b, relationship,
    # standpoint, authority, resolves, source_refs); later as
    # (date, kind, subject, note).
    nodes: tuple
    recs: tuple
    later: tuple
    as_of: str
    frame_subject: str
    needs_memory: bool
    consequential: bool
    abstention_acceptable: bool
    expected_hint: str  # corroborated | weak | stale | conflicting | unknown
    expected_action: str  # HARD_FRAME | SOFT_FRAME | QUERY_ONLY | ...
    source_run: str
    source_scenario: str

    def variant(self) -> str:
        return "dev" if self.scenario_id.startswith("SD-") else "eval"


def _n(node_id, date, project="main", valid_until="", contradicts="",
       references=""):
    return (node_id, date, project, valid_until, contradicts, references)


def _r(rec_id, a, b, rel, standpoint, authority, resolves, refs=()):
    return (rec_id, a, b, rel, standpoint, authority, resolves, refs)


def _l(date, kind, subject, note=""):
    return (date, kind, subject, note)


DEV_SCENARIOS = (
    # same_event + current + ledger authority -> corroborated -> HARD.
    SemScenario("SD-fix-hard", "A", "fix-store", "T4-current-vs-stale",
                (_n("evt-205", "2024-07-11"), _n("adr-007", "2024-07-11")),
                (_r("r1", "evt-205", "adr-007", "same_event", "2024-07-11",
                    "ledger", True, ("adr-007",)),), (),
                "2024-08-23", "evt-205", True, True, False,
                "corroborated", "HARD_FRAME",
                "ch13-dev-v1", "A-fix-dec-dev"),
    SemScenario("SD-ship-hard", "A", "ship-ch10", "T7-release",
                (_n("intent-401", "2024-07-17"), _n("commit-118", "2024-08-27")),
                (_r("r1", "commit-118", "intent-401", "completes", "2024-08-27",
                    "author-merge", True, ("commit-118",)),), (),
                "2024-08-30", "intent-401", True, True, False,
                "corroborated", "HARD_FRAME",
                "ch13-dev-v1", "A-ship-dec-dev"),
    # Agent-authored same_event -> weak -> SOFT.
    SemScenario("SD-prose-soft", "B", "review-prose", "T1-publication",
                (_n("agent-note-1", "2024-07-20"), _n("span-044", "2024-07-20")),
                (_r("r1", "agent-note-1", "span-044", "same_event", "2024-07-20",
                    "agent:reader-1", True, ("span-044",)),), (),
                "2024-08-23", "agent-note-1", True, False, False,
                "weak", "SOFT_FRAME",
                "ch13-dev-v1", "B-prose-weak-dev"),
    SemScenario("SD-cleanup-soft", "D", "corpus-cleanup", None,
                (_n("agent-note-2", "2024-07-20"), _n("span-045", "2024-07-20")),
                (_r("r1", "agent-note-2", "span-045", "same_event", "2024-07-20",
                    "agent:reader-1", True, ("span-045",)),), (),
                "2024-08-23", "agent-note-2", True, True, False,
                "weak", "SOFT_FRAME",
                "ch13-dev-v1", "D-cleanup-conflict-dev"),
    # Expired validity -> stale -> QUERY_ONLY (temporal firewall).
    SemScenario("SD-arch-stale", "C", "review-arch", "T1-architecture",
                (_n("adr-003", "2024-03-01", "main", "2024-07-11"),
                 _n("evt-205", "2024-07-11")),
                (_r("r1", "adr-003", "evt-205", "same_event", "2024-07-11",
                    "ledger", True, ("adr-003",)),), (),
                "2024-12-02", "adr-003", True, True, False,
                "stale", "QUERY_ONLY",
                "ch13-dev-v1", "F-arch-queryonly-dev"),
    # Mutual contradiction + resolves -> conflicting -> QUERY_ONLY.
    SemScenario("SD-cite-conflict", "D", "cite-rule", "T5-support-vs-topicality",
                (_n("claim-a", "2024-07-11", "main", "", "claim-b"),
                 _n("claim-b", "2024-07-12", "main", "", "claim-a")),
                (_r("r1", "claim-a", "claim-b", "same_event", "2024-07-12",
                    "ledger", True, ("claim-a",)),), (),
                "2024-08-23", "claim-a", True, False, False,
                "conflicting", "QUERY_ONLY",
                "ch13-dev-v1", "E-cite-unknown-dev"),
    # Unknown + consequential -> REQUEST (answerable; abstention refused).
    SemScenario("SD-fix-request", "G", "fix-store", "T4-current-vs-stale",
                (_n("span-060", "2024-07-20"),), (), (),
                "2024-08-23", "span-060", True, True, False,
                "unknown", "REQUEST_MORE_EVIDENCE",
                "ch13-dev-v1", "A-fix-dec-dev"),
    # Unknown + abstention acceptable -> ABSTAIN.
    SemScenario("SD-cleanup-abstain", "K", "corpus-cleanup", None,
                (_n("span-061", "2024-07-20"),), (), (),
                "2024-08-23", "span-061", True, True, True,
                "unknown", "ABSTAIN",
                "ch13-dev-v1", "K-cleanup-unknown-dev"),
    # Revocation after standpoint -> invalidated -> stale -> QUERY_ONLY.
    SemScenario("SD-cite-invalid", "D", "cite-rule", "T5-support-vs-topicality",
                (_n("session-508", "2024-06-19"), _n("runbook-509", "2024-08-02")),
                (_r("r1", "session-508", "runbook-509", "same_event", "2024-08-02",
                    "ledger", True, ("runbook-509",)),),
                (_l("2024-09-01", "revocation", "session-508", "withdrawn"),),
                "2024-10-01", "session-508", True, False, False,
                "stale", "QUERY_ONLY",
                "ch13-dev-v1", "G-cite-noproject-dev"),
    # Cross-scope without licence -> unknown -> QUERY_ONLY (quarantine).
    SemScenario("SD-irrel-xscope", "L", "irrelevant", "T1-publication",
                (_n("adr-007", "2024-07-11", "main"),
                 _n("adr-507", "2024-07-11", "atlas")),
                (_r("r1", "adr-007", "adr-507", "same_event", "2024-07-11",
                    "agent:reader-1", True, ("adr-507",)),), (),
                "2024-08-23", "adr-007", False, False, False,
                "unknown", "QUERY_ONLY",
                "ch13-dev-v1", "L-irrel-dec-dev"),
    # Correspondence only: topical agreement, resolves=False -> unknown ->
    # QUERY_ONLY. The anti-promotion case: agreement must never be HARD.
    SemScenario("SD-fix-corresp", "A", "fix-store", "T4-current-vs-stale",
                (_n("session-014", "2024-06-14"), _n("session-019", "2024-06-19")),
                (_r("r1", "session-014", "session-019", "correspondence",
                    "2024-06-19", "ledger", False, ("session-019",)),), (),
                "2024-08-23", "session-014", True, True, False,
                "unknown", "QUERY_ONLY",
                "ch13-dev-v1", "A-fix-dec-dev"),
    # Poison excluded by hard context; corroborated evidence -> HARD.
    SemScenario("SD-poison-hard", "J", "corpus-cleanup", None,
                (_n("evt-205", "2024-07-11"), _n("adr-007", "2024-07-11")),
                (_r("r1", "evt-205", "adr-007", "same_event", "2024-07-11",
                    "ledger", True, ("adr-007",)),), (),
                "2024-08-23", "evt-205", True, True, False,
                "corroborated", "HARD_FRAME",
                "ch13-dev-v1", "J-cleanup-poison-dev"),
)

EVAL_SCENARIOS = (
    SemScenario("SE-arch-hard", "A", "review-arch", "T1-architecture",
                (_n("evt-205", "2024-07-11"), _n("adr-007", "2024-07-11")),
                (_r("r1", "evt-205", "adr-007", "same_event", "2024-07-11",
                    "ledger", True, ("adr-007",)),), (),
                "2024-08-23", "evt-205", True, True, False,
                "corroborated", "HARD_FRAME",
                "ch13-eval-v1", "A-arch-dec-eval"),
    SemScenario("SE-fix-soft", "B", "fix-store", "T4-current-vs-stale",
                (_n("agent-note-3", "2024-07-20"), _n("span-046", "2024-07-20")),
                (_r("r1", "agent-note-3", "span-046", "same_event", "2024-07-20",
                    "agent:reader-1", True, ("span-046",)),), (),
                "2024-08-23", "agent-note-3", True, True, False,
                "weak", "SOFT_FRAME",
                "ch13-eval-v1", "B-fix-weak-eval"),
    SemScenario("SE-arch-stale", "C", "review-arch", "T1-architecture",
                (_n("adr-003", "2024-03-01", "main", "2024-07-11"),
                 _n("evt-205", "2024-07-11")),
                (_r("r1", "adr-003", "evt-205", "same_event", "2024-07-11",
                    "ledger", True, ("adr-003",)),), (),
                "2024-12-02", "adr-003", True, True, False,
                "stale", "QUERY_ONLY",
                "ch13-eval-v1", "C-arch-shift-eval"),
    SemScenario("SE-cite-conflict", "D", "cite-rule", "T5-support-vs-topicality",
                (_n("claim-c", "2024-07-11", "main", "", "claim-d"),
                 _n("claim-d", "2024-07-12", "main", "", "claim-c")),
                (_r("r1", "claim-c", "claim-d", "same_event", "2024-07-12",
                    "ledger", True, ("claim-c",)),), (),
                "2024-08-23", "claim-c", True, False, False,
                "conflicting", "QUERY_ONLY",
                "ch13-eval-v1", "D-cite-conflict-eval"),
    SemScenario("SE-ship-request", "E", "ship-ch10", "T7-release",
                (_n("span-062", "2024-07-20"),), (), (),
                "2024-08-23", "span-062", True, True, False,
                "unknown", "REQUEST_MORE_EVIDENCE",
                "ch13-eval-v1", "E-ship-unknown-eval"),
    SemScenario("SE-prose-floor", "F", "review-prose", "T1-publication",
                (_n("span-063", "2024-07-20"),), (), (),
                "2024-08-23", "span-063", True, False, False,
                "unknown", "QUERY_ONLY",
                "ch13-eval-v1", "F-prose-queryonly-eval"),
    SemScenario("SE-fix-corresp", "A", "fix-store", "T4-current-vs-stale",
                (_n("session-014", "2024-06-14"), _n("session-019", "2024-06-19")),
                (_r("r1", "session-014", "session-019", "correspondence",
                    "2024-06-19", "ledger", False, ("session-019",)),), (),
                "2024-08-23", "session-014", True, True, False,
                "unknown", "QUERY_ONLY",
                "ch13-eval-v1", "B-fix-weak-eval"),
    SemScenario("SE-fix-invalid", "G", "fix-store", "T4-current-vs-stale",
                (_n("session-508", "2024-06-19"), _n("runbook-509", "2024-08-02")),
                (_r("r1", "session-508", "runbook-509", "same_event", "2024-08-02",
                    "ledger", True, ("runbook-509",)),),
                (_l("2024-09-01", "revocation", "session-508", "withdrawn"),),
                "2024-10-01", "session-508", True, True, False,
                "stale", "QUERY_ONLY",
                "ch13-eval-v1", "G-fix-noproject-eval"),
    SemScenario("SE-irrel-xscope", "L", "irrelevant", "T1-publication",
                (_n("adr-007", "2024-07-11", "main"),
                 _n("adr-507", "2024-07-11", "atlas")),
                (_r("r1", "adr-007", "adr-507", "same_event", "2024-07-11",
                    "agent:reader-1", True, ("adr-507",)),), (),
                "2024-08-23", "adr-007", False, False, False,
                "unknown", "QUERY_ONLY",
                "ch13-eval-v1", "L-irrel-weak-eval"),
)


def all_scenarios():
    return list(DEV_SCENARIOS) + list(EVAL_SCENARIOS)


def dev_scenarios():
    return list(DEV_SCENARIOS)


def eval_scenarios():
    return list(EVAL_SCENARIOS)


def split_digests():
    import hashlib
    out = {}
    for name, scenarios in (("dev", DEV_SCENARIOS), ("eval", EVAL_SCENARIOS)):
        blob = "\n".join(repr(s) for s in scenarios).encode()
        out[name] = hashlib.sha256(blob).hexdigest()[:16]
        out[name + "_count"] = len(scenarios)
    return out


REQUIRED_CASES = ("same_event_current", "correspondence_only", "stale",
                  "conflicting", "invalidated", "cross_scope")


def case_of(scenario: SemScenario) -> str:
    """Which positive-control reconciliation case a scenario covers."""
    recs = scenario.recs
    if not recs:
        return "unknown_bare"
    rel = recs[0][3]
    if rel == "correspondence":
        return "correspondence_only"
    later_kinds = {e[1] for e in scenario.later}
    if later_kinds & {"revocation", "contradiction", "supersession"}:
        return "invalidated"
    nodes = {n[0]: n for n in scenario.nodes}
    other = recs[0][2] if recs[0][1] == scenario.frame_subject else recs[0][1]
    subj = nodes[scenario.frame_subject]
    if subj[3] and subj[3] < scenario.as_of:
        return "stale"
    subj_proj = subj[2]
    other_proj = nodes[other][2] if other in nodes else subj_proj
    if subj_proj != other_proj:
        return "cross_scope"
    subj_contra = subj[4]
    other_contra = nodes[other][4] if other in nodes else ""
    if subj_contra or other_contra:
        return "conflicting"
    return "same_event_current"
