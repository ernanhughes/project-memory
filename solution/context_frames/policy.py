"""The context policy: a staged pipeline, not a single learned score.

Stages, in order:

1. **candidate retrieval** -- Chapter 3 hybrid search at high recall. From
   C4 the frame also participates here: the objective runs as a second
   query and is fused with the first, and the classes the ProjectFrame
   prefers for this work type are given a pull, so material the query
   wording never reaches can still become a candidate. A frame that only
   reranks cannot repair what retrieval never surfaced;
2. **signal scoring** -- each component computed and recorded separately,
   for every candidate including the ones about to be dropped;
3. **hard eligibility** -- project scope; supersession when a successor
   is available; class absence without query support;
4. **goal-conditioned ordering** -- candidates are bucketed by the class
   preference the ProjectFrame declares for this work type, and ordered
   by retrieval score within a bucket;
5. **coalescing** -- echo folding, disagreement preservation, temporal
   folding (the full condition only);
6. **budget admission** -- greedy fill of a fixed token budget, with a
   redundancy penalty in the full condition.

A staged pipeline was chosen over a weighted sum because the chapter's
claim is debuggable importance. With stages, a wrong bundle names the
stage that produced it. With one score, it names nothing.

The ladder holds reader, corpus, query and token budget fixed and
changes only how context is built:

``C0`` strong query-only retrieval (the Chapter 3 baseline)
``C1`` C0 plus a recency preference over recent work
``C2`` C0 restricted to the project scope
``C3`` C2 plus the ProjectFrame's default class policy
``C4`` C3 plus the WorkFrame: objective-expanded recall and work-type
       class policy
``C5`` C4 plus the Chapter 7, 8 and 9 signals and their candidate pulls
``C6`` C5 plus Chapter 4/5 adjacency, coalescing and redundancy
``CO`` the ledger oracle: an admission ceiling at this budget, not a
       system
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

from . import signals as sig
from .coalesce import coalesce, passthrough
from .model import (Candidate, ContextBundle, ContextTrace, MemoryUnit,
                    ProjectFrame, WorkFrame)
from .retrieval import HybridRetriever, reciprocal_rank_fusion

POLICY_VERSION = "staged-goal-conditioned-v0.2"
CANDIDATE_POOL = 40
CLASS_PULL_PER_CLASS = 3   # ProjectFrame default; see class_pull_width
CLASS_ABSENT_QUERY_RANK = 10
DEFAULT_BUDGET_TOKENS = 1500   # matches the Chapter 3 6000-character cap


@dataclass(frozen=True)
class Condition:
    name: str
    label: str
    scope_filter: bool = False
    use_recency: bool = False
    class_policy: str = "none"      # none | default | work_type
    expand_with_objective: bool = False
    class_pull: bool = False
    use_layers: bool = False        # Ch7/Ch8/Ch9 signals
    layer_pull: bool = False        # Ch8 successors into the candidate pool
    use_relational: bool = False    # Ch4/Ch5 adjacency
    coalescing: bool = False
    redundancy_penalty: bool = False
    oracle: bool = False
    # Chapter 13 frame-control flags. Both default False, so every
    # pre-existing condition builds byte-identical bundles.
    # soft_frame: keep frame-assisted pool breadth (objective expansion
    #   and class pulls) but disable the hard class-absence exclusion:
    #   the frame may rerank, never hard-exclude the query-only path.
    # flat_rank: rank by retrieval score alone, ignoring frame buckets:
    #   breadth without frame preference (BROADEN mode).
    soft_frame: bool = False
    flat_rank: bool = False


LADDER: tuple[Condition, ...] = (
    Condition("C0", "strong RAG, query only"),
    Condition("C1", "strong RAG + recent work", use_recency=True),
    Condition("C2", "strong RAG + project scope", scope_filter=True),
    Condition("C3", "+ ProjectFrame", scope_filter=True,
              class_policy="default"),
    Condition("C4", "+ WorkFrame", scope_filter=True,
              class_policy="work_type", expand_with_objective=True,
              class_pull=True),
    Condition("C5", "+ Ch7/Ch8/Ch9", scope_filter=True,
              class_policy="work_type", expand_with_objective=True,
              class_pull=True, use_layers=True, layer_pull=True),
    Condition("C6", "full context builder", scope_filter=True,
              class_policy="work_type", expand_with_objective=True,
              class_pull=True, use_layers=True, layer_pull=True,
              use_relational=True, coalescing=True, redundancy_penalty=True),
)

ORACLE = Condition("CO", "ledger oracle (admission ceiling)", oracle=True,
                   scope_filter=True)

CONDITIONS = {c.name: c for c in LADDER + (ORACLE,)}


# --------------------------------------------------------------------------
# Stage 1: candidate retrieval, with the frame allowed to participate.
# --------------------------------------------------------------------------

def _candidate_pool(condition: Condition, query: str, frame: ProjectFrame,
                    work: WorkFrame, retriever: HybridRetriever,
                    units: dict[str, MemoryUnit]) -> tuple[list[str],
                                                           dict[str, float],
                                                           dict]:
    primary = retriever.retrieve(query, CANDIDATE_POOL)
    rankings = [[uid for uid, _ in primary.ranked]]
    detail = {"mode": primary.mode, "query_pool": len(primary.ranked)}

    if condition.expand_with_objective and work.objective:
        secondary = retriever.retrieve(work.objective, CANDIDATE_POOL)
        rankings.append([uid for uid, _ in secondary.ranked])
        detail["objective_pool"] = len(secondary.ranked)

    fused = reciprocal_rank_fusion(rankings) if len(rankings) > 1 else primary.ranked
    scores = sig.normalise_ranked(fused[:CANDIDATE_POOL])
    pool = [uid for uid, _ in fused[:CANDIDATE_POOL]]

    if condition.use_recency:
        recent = sorted(units.values(), key=lambda u: u.event_time,
                        reverse=True)[:8]
        added = [u.unit_id for u in recent if u.unit_id not in scores]
        for unit_id in added:
            pool.append(unit_id)
            scores[unit_id] = 0.05
        detail["recency_added"] = added

    if condition.class_pull:
        prefs = frame.preferences_for(work.work_type)
        pulled: list[str] = []
        floor = min(scores.values(), default=0.05) * 0.5
        for kind in prefs:
            members = [u for u in units.values()
                       if u.kind == kind and u.project_id in frame.scope()]
            members.sort(key=lambda u: (-scores.get(u.unit_id, 0.0), u.unit_id))
            for unit in members[:frame.class_pull_width]:
                if unit.unit_id not in scores:
                    pool.append(unit.unit_id)
                    scores[unit.unit_id] = floor
                    pulled.append(unit.unit_id)
        detail["class_pulled"] = pulled

    if condition.layer_pull:
        # Chapter 8: if a superseded unit is a candidate, its successor must
        # be one too, or the policy can only choose between silence and a
        # stale answer.
        successors: list[str] = []
        for unit_id in list(pool):
            unit = units.get(unit_id)
            if unit is None or not unit.superseded_by:
                continue
            if unit.superseded_by in units and unit.superseded_by not in scores:
                pool.append(unit.superseded_by)
                scores[unit.superseded_by] = scores.get(unit_id, 0.05)
                successors.append(unit.superseded_by)
        detail["successors_pulled"] = successors

    detail["pool"] = len(pool)
    return pool, scores, detail


# --------------------------------------------------------------------------
# Stage 3: signals.
# --------------------------------------------------------------------------

def _score(candidate: Candidate, frame: ProjectFrame, work: WorkFrame,
           condition: Condition, query_score: float) -> None:
    unit = candidate.unit
    s = candidate.signals
    s.query_relevance = round(query_score, 4)
    s.project_relevance = 1.0 if unit.project_id in frame.scope() else 0.0
    s.recency = sig.recency(unit, work.as_of)
    if condition.class_policy == "work_type":
        s.goal_relevance = sig.goal_relevance(unit, frame, work)
    elif condition.class_policy == "default":
        s.goal_relevance = sig.goal_relevance(
            unit, frame, replace(work, work_type="default"))
    if condition.use_layers:
        s.temporal_validity = sig.temporal_validity(unit, work.as_of)
        s.evidence_strength = sig.evidence_strength(unit)
        s.open_loop_relevance = sig.open_loop_relevance(unit, frame, work)

    score = s.query_relevance
    if condition.use_recency:
        score *= 0.5 + 0.5 * s.recency
    if condition.use_layers:
        score *= s.temporal_validity * s.evidence_strength
        score += 0.15 * s.open_loop_relevance
    candidate.stage_score = round(score, 5)


def _bucket(candidate: Candidate, frame: ProjectFrame, work: WorkFrame,
            condition: Condition) -> int:
    if condition.class_policy == "none":
        return 0
    work_type = (work.work_type if condition.class_policy == "work_type"
                 else "default")
    return sig.goal_tier(candidate.unit, frame, work_type)


# --------------------------------------------------------------------------

def build_context(condition_name: str | Condition, query: str,
                  frame: ProjectFrame,
                  work: WorkFrame, retriever: HybridRetriever,
                  units: dict[str, MemoryUnit],
                  budget_tokens: int = DEFAULT_BUDGET_TOKENS,
                  trace_id: str = "", task=None) -> tuple[ContextBundle,
                                                           ContextTrace]:
    # Chapter 13 passes Condition objects directly (soft/flat frame
    # modes); every prior caller passes a registry name. Both paths
    # share all downstream stages.
    condition = (CONDITIONS[condition_name]
                 if isinstance(condition_name, str) else condition_name)
    started = time.perf_counter()
    trace = ContextTrace(
        trace_id=trace_id or f"{work.work_frame_id}-{condition_name}",
        condition=condition_name, policy_version=POLICY_VERSION,
        project_frame=frame.frame_id(), work_frame=work.work_frame_id,
        query=query, as_of=work.as_of, budget_tokens=budget_tokens,
        retriever=retriever.describe())

    if condition.oracle:
        return _oracle_bundle(task, frame, units, budget_tokens, trace,
                              started)

    pool, query_scores, detail = _candidate_pool(
        condition, query, frame, work, retriever, units)
    trace.stages.append({"stage": "retrieve", **detail})

    candidates = [Candidate(unit=units[uid], retrieval_rank=i + 1)
                  for i, uid in enumerate(pool) if uid in units]
    query_rank = {uid: i + 1 for i, uid in enumerate(
        sorted(query_scores, key=lambda u: -query_scores[u]))}

    # Stage 2: signals, computed for every candidate including the ones
    # about to be dropped. A trace that reports zeroes for a rejected
    # candidate cannot show that a highly relevant unit was excluded on
    # other grounds, which is most of what a rejection needs to explain.
    for candidate in candidates:
        _score(candidate, frame, work, condition,
               query_scores.get(candidate.unit_id, 0.0))

    # Stage 3: hard eligibility.
    eligible: list[Candidate] = []
    for candidate in candidates:
        unit = candidate.unit
        if condition.scope_filter and unit.project_id not in frame.scope():
            _drop(candidate, "OUT_OF_PROJECT_SCOPE")
            continue
        if (condition.use_layers and frame.penalise_stale
                and not unit.is_current(work.as_of)
                and unit.superseded_by in query_scores):
            _drop(candidate, "SUPERSEDED_SUCCESSOR_AVAILABLE")
            continue
        if condition.class_policy != "none" and not condition.soft_frame:
            tier = _bucket(candidate, frame, work, condition)
            if (tier == sig.ABSENT_TIER
                    and query_rank.get(unit.unit_id, 999)
                    > CLASS_ABSENT_QUERY_RANK):
                _drop(candidate, "CLASS_ABSENT_AND_LOW_QUERY_RELEVANCE")
                continue
        elif condition.soft_frame:
            # Soft frame records the tier judgement without excluding:
            # the exclusion the wrong-frame hazard measurement blames
            # is disabled here, visibly, per candidate.
            tier = _bucket(candidate, frame, work, condition)
            if tier == sig.ABSENT_TIER:
                candidate.reason_codes.append(
                    "CLASS_ABSENT_BUT_RETAINED_SOFT_FRAME")
        eligible.append(candidate)
    trace.stages.append({"stage": "eligibility", "kept": len(eligible),
                         "dropped": len(candidates) - len(eligible)})

    # Stage 4: goal-conditioned ordering (flat under BROADEN: breadth
    # without frame preference keeps retrieval-score order).
    for candidate in eligible:
        candidate.reason_codes.append(
            f"CLASS_TIER_{_bucket(candidate, frame, work, condition)}")
    if condition.flat_rank:
        ranked = sorted(
            eligible,
            key=lambda c: (-c.stage_score, c.unit_id))
        trace.stages.append({"stage": "rank", "policy": "flat-retrieval",
                             "ranked": len(ranked)})
    else:
        ranked = sorted(
            eligible,
            key=lambda c: (_bucket(c, frame, work, condition),
                           -c.stage_score, c.unit_id))
        trace.stages.append({"stage": "rank",
                             "policy": condition.class_policy,
                             "ranked": len(ranked)})

    # Stages 5 and 6.
    if condition.coalescing:
        items, admitted_ids = _admit_coalesced(ranked, budget_tokens, trace)
    else:
        items, admitted_ids = _admit_units(ranked, budget_tokens, condition)

    if condition.use_relational:
        for candidate in ranked:
            candidate.signals.relational_relevance = sig.relational_relevance(
                candidate.unit, admitted_ids)

    bundle = ContextBundle(bundle_id=f"cb-{trace.trace_id}", items=items,
                           budget_tokens=budget_tokens,
                           condition=condition_name)
    trace.candidates = candidates
    trace.bundle_digest = bundle.digest()
    trace.bundle_tokens = bundle.tokens
    trace.latency_ms = (time.perf_counter() - started) * 1000.0
    trace.stages.append({"stage": "budget", "admitted_items": len(items),
                         "bundle_tokens": bundle.tokens,
                         "budget_tokens": budget_tokens})
    return bundle, trace


def _drop(candidate: Candidate, code: str) -> None:
    candidate.eligible = False
    candidate.decision = "reject"
    candidate.reason_codes.append(code)


def _admit_units(ranked: list[Candidate], budget: int,
                 condition: Condition) -> tuple[list, set[str]]:
    admitted: list[Candidate] = []
    spent = 0
    for candidate in ranked:
        if condition.redundancy_penalty:
            candidate.signals.redundancy = sig.redundancy(
                candidate.unit, [c.unit for c in admitted])
            if candidate.signals.redundancy > 0.6:
                candidate.decision = "reject"
                candidate.reason_codes.append("REDUNDANT_WITH_ADMITTED")
                continue
        if spent + candidate.unit.tokens > budget and admitted:
            candidate.decision = "reject"
            candidate.reason_codes.append("BUDGET_EXHAUSTED")
            continue
        candidate.decision = "admit"
        candidate.reason_codes.append("ADMITTED_WITHIN_BUDGET")
        admitted.append(candidate)
        spent += candidate.unit.tokens
    items, _ = passthrough(admitted)
    return items, {c.unit_id for c in admitted}


def _admit_coalesced(ranked: list[Candidate], budget: int,
                     trace: ContextTrace) -> tuple[list, set[str]]:
    bundle_items, operations = coalesce(ranked)
    trace.stages.append({"stage": "coalesce", "operations": operations,
                         "items": len(bundle_items)})
    items = []
    admitted_ids: set[str] = set()
    spent = 0
    for item in bundle_items:
        if spent + item.tokens > budget and items:
            continue
        items.append(item)
        spent += item.tokens
        admitted_ids.update(item.members)
    for candidate in ranked:
        if candidate.unit_id in admitted_ids:
            candidate.decision = "admit"
            if candidate.coalesced_into is None:
                candidate.reason_codes.append("ADMITTED_WITHIN_BUDGET")
        else:
            candidate.decision = "reject"
            candidate.reason_codes.append("BUDGET_EXHAUSTED")
    return items, admitted_ids


def _oracle_bundle(task, frame: ProjectFrame, units: dict[str, MemoryUnit],
                   budget: int, trace: ContextTrace,
                   started: float) -> tuple[ContextBundle, ContextTrace]:
    """The ceiling: admit required evidence, then helpful evidence.

    This is not a memory system. It reads the hidden ledger and shows
    what the budget physically permits, so the ladder's numbers can be
    read against an attainable maximum rather than against 1.0.
    """
    from .fixtures import MUST, SHOULD
    order = [u for u, lab in task.ledger.items() if lab == MUST]
    order += [u for u, lab in task.ledger.items() if lab == SHOULD]
    admitted: list[Candidate] = []
    spent = 0
    for unit_id in order:
        unit = units.get(unit_id)
        if unit is None:
            continue
        if spent + unit.tokens > budget and admitted:
            continue
        candidate = Candidate(unit=unit, decision="admit",
                              reason_codes=["ORACLE_LEDGER"])
        admitted.append(candidate)
        spent += unit.tokens
    items, _ = passthrough(admitted)
    bundle = ContextBundle(bundle_id=f"cb-{trace.trace_id}", items=items,
                           budget_tokens=budget, condition="CO")
    trace.candidates = admitted
    trace.bundle_digest = bundle.digest()
    trace.bundle_tokens = bundle.tokens
    trace.latency_ms = (time.perf_counter() - started) * 1000.0
    trace.stages.append({"stage": "oracle", "admitted_items": len(items),
                         "bundle_tokens": bundle.tokens})
    return bundle, trace
