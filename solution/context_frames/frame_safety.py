"""Frame safety: establish the frame from evidence, then choose how
strongly it may control retrieval.

Chapter 10 showed a correct declared frame helps context selection
while a wrong frame can select worse than no frame (E10-J). Chapter 12
showed memory moves behaviour in both directions, including harmful
actions. This module answers the question those two results force:

> How strongly should the system trust its own understanding of what
> it is doing?

Two sub-questions, kept separate:

1. **Frame establishment** — why does the system believe this frame?
   A deterministic staged gate over observable work signals yields an
   establishment class (DECLARED / CORROBORATED / INFERRED /
   CONFLICTING / STALE / UNKNOWN). No scalar confidence, no model
   self-report: QuCo-RAG and AdaRAGUE both warn that self-confidence
   is unreliable, so trust is derived from signal evidence.
2. **Frame-control policy** — given the establishment class, which
   retrieval mode may run? HARD (status quo), SOFT (frame reranks but
   cannot hard-exclude), QUERY_ONLY (Ch3 path as safe mode), BROADEN
   (breadth without frame preference), REQUEST / ABSTAIN (decline to
   act under uncertainty about consequential work).

Reason codes arise from actual control flow, never post-hoc prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import signals as sig
from .frames import CUES
from .model import ProjectFrame, WorkFrame, WorkSignal
from .policy import Condition

FRAME_ESTABLISHMENT_VERSION = "frame-establishment-v1"
FRAME_POLICY_VERSION = "safe-frame-policy-v1"

# Establishment classes, strongest first (CONFLICTING/STALE/UNKNOWN are
# disqualifiers, not strengths — precedence handles that).
DECLARED = "DECLARED"
CORROBORATED = "CORROBORATED"
INFERRED = "INFERRED"
CONFLICTING = "CONFLICTING"
STALE = "STALE"
UNKNOWN = "UNKNOWN"

# Policy actions.
HARD_FRAME = "HARD_FRAME"
SOFT_FRAME = "SOFT_FRAME"
QUERY_ONLY = "QUERY_ONLY"
BROADEN = "BROADEN_RETRIEVAL"
REQUEST_MORE = "REQUEST_MORE_EVIDENCE"
ABSTAIN = "ABSTAIN"

# Signal kinds that can directly declare current work. Everything else
# is corroborating at best. Workflow metadata is a system record: it
# is credible enough to contradict (stale state looks authoritative),
# never enough to establish on its own.
DIRECT_KINDS = ("user_message", "agent_task", "scheduled_job")
CORROBORATING_KINDS = ("project_state", "tool_result", "test_failure",
                       "event")
PROJECT_IDS = ("memory-book", "writer", "cocder")

# Action-schema entries whose effects are destructive or
# state-corrupting (observable from the schema — no hidden labels).
# SHIP_CHAPTER is deliberately excluded: grader v2 scores premature
# shipment as a reversible governance error, not a harmful event.
HIGH_STAKES_ACTIONS = ("DELETE_FACADE", "SET_BACKEND", "MIGRATE_CALLERS",
                       "UPDATE_DOCS", "REGENERATE_FIXTURES")


# --------------------------------------------------------------------------
# Evidence: one assessed signal.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FrameEvidence:
    signal_id: str
    source_type: str
    observed_at: str
    project_id: str | None
    proposed_work_type: str | None
    directness: str          # DIRECT | CORROBORATING | INDIRECT
    current: bool            # observed_at <= standpoint

    def to_dict(self) -> dict:
        return {"signal_id": self.signal_id,
                "source_type": self.source_type,
                "observed_at": self.observed_at,
                "project_id": self.project_id,
                "proposed_work_type": self.proposed_work_type,
                "directness": self.directness,
                "current": self.current}


def _cue_hits(text: str, work_type: str) -> int:
    blob = text.lower()
    return sum(1 for cue in CUES.get(work_type, ()) if cue in blob)


def _project_in(text: str) -> str | None:
    blob = text.lower()
    for pid in PROJECT_IDS:
        if pid in blob:
            return pid
    return None


def assess_signal(signal: WorkSignal, project: ProjectFrame,
                  as_of: str) -> FrameEvidence:
    """Classify one signal's evidential standing, deterministically.

    A signal proposes the cue-count winning work type among the ones
    the ProjectFrame declares. Directness is a function of channel
    kind and cue overlap — never of model judgement.
    """
    known = project.known_work_types()
    scored = sorted(
        ((wt, _cue_hits(signal.text, wt)) for wt in known),
        key=lambda kv: (-kv[1], kv[0]))
    proposed = scored[0][0] if scored and scored[0][1] > 0 else None
    if signal.kind in DIRECT_KINDS and proposed is not None:
        # A direct channel must carry real content: at least two cue
        # hits, so a passing mention cannot declare a frame.
        directness = ("DIRECT" if _cue_hits(signal.text, proposed) >= 2
                      else "INDIRECT")
    elif signal.kind in CORROBORATING_KINDS and (
            proposed is not None or _project_in(signal.text)):
        directness = "CORROBORATING"
    else:
        directness = "INDIRECT"
    current = (not signal.observed_at) or signal.observed_at <= as_of
    return FrameEvidence(
        signal_id=signal.signal_id, source_type=signal.kind,
        observed_at=signal.observed_at,
        project_id=_project_in(signal.text), proposed_work_type=proposed,
        directness=directness, current=current)


# --------------------------------------------------------------------------
# Decision + trace.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FrameDecision:
    establishment: str
    selected_work_type: str | None
    selected_project: str | None
    action: str
    reasons: tuple[str, ...]
    supporting_refs: tuple[str, ...]
    conflicting_refs: tuple[str, ...]
    high_stakes: bool

    def to_dict(self) -> dict:
        return {"establishment": self.establishment,
                "selected_work_type": self.selected_work_type,
                "selected_project": self.selected_project,
                "action": self.action,
                "reasons": list(self.reasons),
                "supporting_refs": list(self.supporting_refs),
                "conflicting_refs": list(self.conflicting_refs),
                "high_stakes": self.high_stakes,
                "establishment_version": FRAME_ESTABLISHMENT_VERSION,
                "policy_version": FRAME_POLICY_VERSION}


@dataclass
class FrameTrace:
    """Frozen account of one frame-establishment decision.

    Retrieval paths invoked and the final bundle hash are filled by
    the experiment driver after context construction; everything else
    is decided here, deterministically, before any retrieval runs.
    """
    trace_id: str
    task_id: str
    scenario_id: str
    evidence: list[dict] = field(default_factory=list)
    candidate_frames: list[dict] = field(default_factory=list)
    signals_considered: int = 0
    signals_rejected_stale: int = 0
    decision: dict | None = None
    policy_action: str = ""
    fallback_mode: str = ""
    retrieval_paths: list[str] = field(default_factory=list)
    bundle_hash: str = ""
    bundle_tokens: int = 0

    def to_dict(self) -> dict:
        return {"trace_id": self.trace_id, "task_id": self.task_id,
                "scenario_id": self.scenario_id,
                "evidence": self.evidence,
                "candidate_frames": self.candidate_frames,
                "signals_considered": self.signals_considered,
                "signals_rejected_stale": self.signals_rejected_stale,
                "decision": self.decision,
                "policy_action": self.policy_action,
                "fallback_mode": self.fallback_mode,
                "retrieval_paths": self.retrieval_paths,
                "bundle_hash": self.bundle_hash,
                "bundle_tokens": self.bundle_tokens,
                "establishment_version": FRAME_ESTABLISHMENT_VERSION,
                "policy_version": FRAME_POLICY_VERSION}


# --------------------------------------------------------------------------
# Staged establishment gate. No scalars, no model calls.
# --------------------------------------------------------------------------

def classify_establishment(signals: tuple[WorkSignal, ...],
                           project: ProjectFrame,
                           as_of: str,
                           action_schema: tuple[str, ...] = (),
                           prior_basis_ids: tuple[str, ...] = ()
                           ) -> tuple[FrameDecision, FrameTrace]:
    """Run stages F0–F5 over observable signals.

    F0 project known?  F1 direct current objective?  F2 independent
    corroboration?  F3 credible conflict?  F4 superseding signal
    (stale prior)?  F5 task stakes from the observable action schema.
    Precedence: CONFLICTING > STALE > UNKNOWN > INFERRED >
    CORROBORATED > DECLARED.
    """
    trace = FrameTrace(trace_id="", task_id="", scenario_id="")
    evidence = [assess_signal(s, project, as_of) for s in signals]
    trace.evidence = [e.to_dict() for e in evidence]
    trace.signals_considered = len(evidence)
    current = [e for e in evidence if e.current]
    trace.signals_rejected_stale = len(evidence) - len(current)

    high_stakes = any(a in HIGH_STAKES_ACTIONS for a in action_schema)

    # F0: project known? A single named project also scopes
    # project-silent evidence: work typing happens inside one project,
    # so evidence without a project tag attaches to the known one
    # rather than fragmenting into phantom candidates.
    projects = {e.project_id for e in current if e.project_id}
    project_known = len(projects) == 1
    if not project_known:
        return _decide(UNKNOWN, None, None, current, (),
                       ("F0_PROJECT_AMBIGUOUS"
                        if projects else "F0_NO_PROJECT_SIGNAL",),
                       high_stakes, trace)
    only_project = next(iter(projects))
    current = [e if e.project_id is not None else FrameEvidence(
        signal_id=e.signal_id, source_type=e.source_type,
        observed_at=e.observed_at, project_id=only_project,
        proposed_work_type=e.proposed_work_type,
        directness=e.directness, current=e.current)
        for e in current]

    # Candidate frames: (project, work_type) pairs with any current
    # non-weak support. INDIRECT-only support still proposes (weakly).
    groups: dict[tuple[str | None, str], list[FrameEvidence]] = {}
    for e in current:
        if e.proposed_work_type is None:
            continue
        key = (e.project_id, e.proposed_work_type)
        groups.setdefault(key, []).append(e)
    trace.candidate_frames = [
        {"project": k[0], "work_type": k[1],
         "signals": [e.signal_id for e in v],
         "direct": any(e.directness == "DIRECT" for e in v)}
        for k, v in sorted(groups.items(),
                           key=lambda kv: (kv[0][0] or "", kv[0][1]))]

    # No candidate at all: nothing current proposes any work. This is
    # the underspecified-task case (family E/F) — UNKNOWN, not a crash.
    if not groups:
        return _decide(UNKNOWN, None, None, current, (),
                       ("F1_NO_DIRECT_OBJECTIVE",), high_stakes, trace)

    # Leading candidate: most DIRECT support, then most signals, then
    # lexical order. Deterministic; ties recorded in the trace.
    def strength(item: tuple[tuple[str | None, str], list]) -> tuple:
        _, members = item
        direct = sum(1 for e in members if e.directness == "DIRECT")
        return (direct, len(members))
    ranked = sorted(groups.items(),
                    key=lambda kv: (-strength(kv)[0], -strength(kv)[1],
                                    kv[0][0] or "", kv[0][1]))
    (lead_project, lead_work), lead_members = ranked[0]
    lead_direct = [e for e in lead_members if e.directness == "DIRECT"]

    # F3: credible conflict? A DIRECT/CORROBORATING signal — or stale
    # workflow metadata, which looks authoritative — backing a
    # different frame than the DIRECT-led candidate.
    if lead_direct:
        rivals: list[FrameEvidence] = []
        for (proj, wt), members in groups.items():
            if (proj, wt) == (lead_project, lead_work):
                continue
            for e in members:
                sig_kind = _signal_kind(signals, e.signal_id)
                if (e.directness in ("DIRECT", "CORROBORATING")
                        or sig_kind == "workflow_metadata"):
                    rivals.append(e)
        if rivals:
            return _decide(
                CONFLICTING, lead_work, lead_project, current,
                tuple(e.signal_id for e in lead_direct),
                ("F3_DIRECT_VS_CREDIBLE_RIVAL",
                 "F3_RIVAL_" + "+".join(sorted(
                     {e.signal_id for e in rivals}))),
                high_stakes, trace,
                conflicting=tuple(sorted({e.signal_id for e in rivals})))

    # F4 supersession is judged by classify_shift(), which takes the
    # prior frame explicitly (staleness is relative to a specific
    # prior, not derivable from a bare signal set). Here a newer
    # DIRECT signal simply competes normally: recency is evidence,
    # not a veto. prior_basis_ids is accepted for interface symmetry
    # and ignored.
    _ = prior_basis_ids

    # F1/F2: strength of the leading candidate.
    kinds = {e.source_type for e in lead_members
             if e.directness in ("DIRECT", "CORROBORATING")}
    if lead_direct and any(
            e.source_type in ("user_message", "agent_task",
                              "scheduled_job") for e in lead_direct):
        return _decide(DECLARED, lead_work, lead_project, current,
                       tuple(e.signal_id for e in lead_direct),
                       ("F1_DIRECT_DECLARATION",), high_stakes, trace)
    if len(kinds) >= 2:
        return _decide(
            CORROBORATED, lead_work, lead_project, current,
            tuple(e.signal_id for e in lead_members),
            ("F2_INDEPENDENT_AGREEMENT",), high_stakes, trace)
    if not current or not groups:
        return _decide(UNKNOWN, None, None, current, (),
                       ("F1_NO_DIRECT_OBJECTIVE",), high_stakes, trace)
    return _decide(INFERRED, lead_work, lead_project, current,
                   tuple(e.signal_id for e in lead_members),
                   ("F1_INDIRECT_ONLY",), high_stakes, trace)


def _signal_kind(signals: tuple[WorkSignal, ...], signal_id: str) -> str:
    for s in signals:
        if s.signal_id == signal_id:
            return s.kind
    return ""


def _decide(establishment: str, work_type: str | None,
            project_id: str | None,
            current: list[FrameEvidence], supporting: tuple[str, ...],
            reasons: tuple[str, ...], high_stakes: bool,
            trace: FrameTrace,
            conflicting: tuple[str, ...] = ()) -> tuple[FrameDecision,
                                                        FrameTrace]:
    action = select_action(establishment, high_stakes)
    decision = FrameDecision(
        establishment=establishment, selected_work_type=work_type,
        selected_project=project_id, action=action, reasons=reasons,
        supporting_refs=supporting, conflicting_refs=conflicting,
        high_stakes=high_stakes)
    trace.decision = decision.to_dict()
    trace.policy_action = action
    return decision, trace


def select_action(establishment: str, high_stakes: bool) -> str:
    """Policy mapping v1: establishment class (+ observable stakes)
    to frame-control action. Frozen before evaluation; changes go
    through backtest discipline, never silent edits."""
    if establishment in (DECLARED, CORROBORATED):
        return HARD_FRAME
    if establishment == INFERRED:
        return SOFT_FRAME
    if establishment in (CONFLICTING, STALE):
        return QUERY_ONLY
    # UNKNOWN: reversible work falls back to query-only retrieval;
    # consequential work must not proceed on an unestablished frame.
    return REQUEST_MORE if high_stakes else QUERY_ONLY


def classify_shift(signals: tuple[WorkSignal, ...],
                   project: ProjectFrame, as_of: str,
                   prior_work_type: str,
                   prior_basis_ids: tuple[str, ...],
                   action_schema: tuple[str, ...] = ()
                   ) -> tuple[FrameDecision, FrameTrace]:
    """F4 variant: judge a PRIOR frame against newer signals.

    If a current DIRECT signal newer than every prior basis signal
    proposes different work, the prior frame is STALE. Otherwise the
    prior frame is re-judged by the standard gate over the full
    signal set (a newer corroborating signal keeps it current).
    """
    evidence = [assess_signal(s, project, as_of) for s in signals]
    current = [e for e in evidence if e.current]
    high_stakes = any(a in HIGH_STAKES_ACTIONS for a in action_schema)
    trace = FrameTrace(trace_id="", task_id="", scenario_id="")
    trace.evidence = [e.to_dict() for e in evidence]
    trace.signals_considered = len(evidence)
    trace.signals_rejected_stale = len(evidence) - len(current)
    basis_times = [e.observed_at for e in current
                   if e.signal_id in prior_basis_ids and e.observed_at]
    for e in sorted(current, key=lambda x: x.observed_at or ""):
        if (e.directness == "DIRECT" and e.observed_at
                and (not basis_times or e.observed_at > max(basis_times))
                and e.signal_id not in prior_basis_ids
                and e.proposed_work_type is not None
                and e.proposed_work_type != prior_work_type):
            return _decide(
                STALE, prior_work_type,
                next((x.project_id for x in current
                      if x.signal_id in prior_basis_ids), None),
                current, tuple(sorted(prior_basis_ids)),
                ("F4_SUPERSEDED_BY_" + e.signal_id,), high_stakes, trace)
    # No supersession: judge the full set normally.
    decision, sub = classify_establishment(
        signals, project, as_of, action_schema)
    trace.candidate_frames = sub.candidate_frames
    trace.signals_rejected_stale = sub.signals_rejected_stale
    trace.decision = sub.decision
    trace.policy_action = sub.policy_action
    return decision, trace


# --------------------------------------------------------------------------
# Mode application: establishment decision -> concrete Condition.
# --------------------------------------------------------------------------

def condition_for_action(action: str) -> Condition:
    """Map a policy action to retrieval-construction flags.

    HARD reuses the Chapter 10 C5 condition unchanged. SOFT keeps the
    frame-assisted pool but disables class-absence exclusion. BROADEN
    additionally drops frame-tiered ranking. QUERY_ONLY is byte-
    equivalent to the Chapter 3 C0 path. REQUEST/ABSTAIN produce no
    bundle (empty context + reason); behaviour is scored as abstention.

    SOFT/BROADEN conditions are passed to build_context as objects;
    the shared CONDITIONS registry is never mutated (a regression
    test pins its exact key set).
    """
    from .policy import CONDITIONS
    base = CONDITIONS["C5"]
    if action == HARD_FRAME:
        return base
    if action == SOFT_FRAME:
        return Condition(name="C5-soft", label="C5, no class exclusion",
                         scope_filter=base.scope_filter,
                         class_policy=base.class_policy,
                         expand_with_objective=base.expand_with_objective,
                         class_pull=base.class_pull,
                         use_layers=base.use_layers,
                         layer_pull=base.layer_pull,
                         soft_frame=True)
    if action == BROADEN:
        return Condition(name="C5-broad", label="C5, flat rank, no exclusion",
                         scope_filter=base.scope_filter,
                         class_policy=base.class_policy,
                         expand_with_objective=base.expand_with_objective,
                         class_pull=base.class_pull,
                         use_layers=base.use_layers,
                         layer_pull=base.layer_pull,
                         soft_frame=True, flat_rank=True)
    if action == QUERY_ONLY:
        return CONDITIONS["C0"]
    raise ValueError(f"no retrieval condition for action {action!r}")


def build_selected_frame(work_type: str, project: ProjectFrame,
                         signals: tuple[WorkSignal, ...],
                         supporting_refs: tuple[str, ...],
                         frame_id: str, as_of: str,
                         objective: str = "") -> WorkFrame:
    """Assemble the gate-selected frame. Derivation is always
    "inferred": the system built it from signals. Declared (person-
    written) frames come from fixtures, never from this function."""
    from .frames import _first_sentence
    refs = supporting_refs or tuple(s.signal_id for s in signals)
    return WorkFrame(
        work_frame_id=frame_id, project_id=project.project_id,
        objective=objective or _first_sentence(signals),
        work_type=work_type, as_of=as_of, signals=signals,
        provenance=(("objective", refs), ("work_type", refs)),
        derivation="inferred")
