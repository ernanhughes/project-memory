"""Unit tests for the context-frames layer.

No services: the retriever runs lexical-only, which is weaker than the
reported configuration and is labelled as such by ``describe()``. These
tests check structure and invariants, never the reported numbers -- those
belong to the frozen runs.
"""

from __future__ import annotations

import pytest

from context_frames import fixtures as fx
from context_frames import metrics as M
from context_frames import signals as sig
from context_frames.backtest import backtest
from context_frames.coalesce import coalesce
from context_frames.corpus import by_id, corpus, corpus_digest
from context_frames.experiments import Harness
from context_frames.frames import keyword_work_frame
from context_frames.model import Candidate, WorkFrame
from context_frames.policy import CONDITIONS, LADDER


@pytest.fixture(scope="module")
def harness() -> Harness:
    return Harness(use_embeddings=False)


# --------------------------------------------------------------------------
# Fixtures and corpus integrity
# --------------------------------------------------------------------------

def test_ledger_audit_is_clean():
    audit = fx.audit_ledgers()
    assert audit.unknown_units == []
    assert audit.out_of_scope_required == []
    assert audit.empty_required == []


def test_corpus_digest_is_stable():
    assert corpus_digest() == corpus_digest()
    assert len(corpus()) == len({u.unit_id for u in corpus()})


def test_echo_units_point_at_a_real_non_echo_source():
    units = by_id()
    for unit in corpus():
        if unit.echo_of is None:
            continue
        assert unit.echo_of in units, unit.unit_id
        assert units[unit.echo_of].evidence_role != "echo", unit.unit_id


def test_superseded_units_name_a_current_successor():
    units = by_id()
    for unit in corpus():
        if unit.valid_until is None:
            continue
        assert unit.superseded_by in units, unit.unit_id
        assert units[unit.superseded_by].valid_until is None, unit.unit_id


def test_no_unit_carries_a_stored_priority():
    for unit in corpus():
        assert not hasattr(unit, "priority")


# --------------------------------------------------------------------------
# Frames
# --------------------------------------------------------------------------

def test_project_frame_is_configuration_not_context():
    frame = fx.PF_MEMORY_BOOK()
    blob = " ".join(frame.objectives + frame.constraints + (frame.purpose,))
    assert "chapter 10" not in blob.lower()
    assert frame.known_work_types()


def test_work_frame_cites_the_signals_behind_each_field():
    work = fx.WF_T1_ARCHITECTURE()
    assert work.unprovenanced_fields() == ()
    signal_ids = {s.signal_id for s in work.signals}
    for _, refs in work.provenance:
        assert set(refs) <= signal_ids


def test_work_frame_needs_no_prompt():
    """A scheduled job and a failing test build frames like any message."""
    frame = fx.PF_MEMORY_BOOK()
    for builder in (fx.WF_T4, fx.WF_T7_RELEASE):
        work = builder()
        assert work.signals
        assert work.signals[0].kind in ("test_failure", "scheduled_job")
    inferred = keyword_work_frame("wf-kw", frame, fx.WF_T7_RELEASE().signals,
                                  fx.AS_OF)
    assert inferred.derivation == "inferred"
    assert inferred.work_type in frame.known_work_types()


# --------------------------------------------------------------------------
# Policy stages
# --------------------------------------------------------------------------

def test_scope_filter_removes_other_projects(harness):
    task = fx.T2(fx.MEMORY_BOOK)
    _, c0, _ = harness.score("C0", task)
    _, c2, trace = harness.score("C2", task)
    units = by_id()
    assert all(units[u].project_id == fx.MEMORY_BOOK for u in c2.unit_ids())
    rejected = {c.unit_id for c in trace.rejected()
                if "OUT_OF_PROJECT_SCOPE" in c.reason_codes}
    assert rejected


def test_every_candidate_has_a_decision_and_a_reason(harness):
    task = fx.T1_ARCHITECTURE()
    _, _, trace = harness.score("C6", task)
    for candidate in trace.candidates:
        assert candidate.decision in ("admit", "reject")
        assert candidate.reason_codes


def test_trace_answers_why_for_admitted_and_rejected(harness):
    task = fx.T1_ARCHITECTURE()
    _, bundle, trace = harness.score("C6", task)
    admitted = bundle.unit_ids()[0]
    assert trace.why(admitted)["decision"] == "admit"
    assert trace.rejected()
    assert trace.why(trace.rejected()[0].unit_id)["decision"] == "reject"


def test_rejected_candidates_keep_their_decision_evidence(harness):
    """A trace that zeroes rejected candidates cannot explain a miss.

    Signals are computed before eligibility for exactly this reason: a
    unit dropped for being superseded or out of scope must still show how
    relevant it was, or the trace answers what was seen and not why the
    needed thing was missed.
    """
    task = fx.T4()
    _, _, trace = harness.score("C6", task)
    dropped = [c for c in trace.candidates if not c.eligible]
    assert dropped, "fixture should drop at least one candidate"
    assert any(c.signals.query_relevance > 0.0 for c in dropped), (
        "every rejected candidate recorded zero query relevance")
    for candidate in dropped:
        assert candidate.reason_codes
        assert candidate.retrieval_rank > 0
        assert candidate.to_dict()["signals"]


def test_bundle_never_exceeds_its_budget(harness):
    for task in fx.all_tasks():
        for condition in LADDER:
            bundle, _ = harness.build(condition.name, task)
            assert bundle.tokens <= bundle.budget_tokens, (
                task.task_id, condition.name)


def test_bundle_construction_is_deterministic(harness):
    task = fx.T1_ARCHITECTURE()
    digests = {harness.build("C6", task)[0].digest() for _ in range(3)}
    assert len(digests) == 1


def test_signal_order_and_irrelevant_signals_do_not_change_selection(harness):
    from dataclasses import replace
    task = fx.T1_ARCHITECTURE()
    base = task.work_frame
    bundle, _ = harness.build("C6", task)
    permuted = replace(base, signals=tuple(reversed(base.signals)))
    noisy = replace(base, signals=base.signals + (fx.S_NOISE,))
    assert harness.build("C6", task, work=permuted)[0].digest() == bundle.digest()
    assert harness.build("C6", task, work=noisy)[0].digest() == bundle.digest()


def test_changing_the_objective_changes_the_bundle(harness):
    pub, arch = fx.T1_PUBLICATION(), fx.T1_ARCHITECTURE()
    b_pub, _ = harness.build("C6", pub)
    b_arch, _ = harness.build("C6", arch)
    assert b_pub.digest() != b_arch.digest()
    assert M.jaccard(b_pub.unit_ids(), b_arch.unit_ids()) < 0.5


# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------

def test_superseded_units_score_below_current_ones():
    units = by_id()
    assert sig.temporal_validity(units["mb-stale-sqlite"], fx.AS_OF) < 1.0
    assert sig.temporal_validity(units["mb-impl-postgres"], fx.AS_OF) == 1.0


def test_echo_scores_below_its_source():
    units = by_id()
    assert (sig.evidence_strength(units["mb-echo-baseline-1"])
            < sig.evidence_strength(units["mb-method-earn"]))


def test_open_loop_relevance_depends_on_the_work_type():
    units = by_id()
    frame = fx.PF_MEMORY_BOOK()
    loop = units["mb-loop-readme-drift"]
    release = sig.open_loop_relevance(loop, frame, fx.WF_T7_RELEASE())
    publication = sig.open_loop_relevance(loop, frame, fx.WF_T7_PUBLICATION())
    assert release > publication == 0.0


# --------------------------------------------------------------------------
# Coalescing
# --------------------------------------------------------------------------

def _candidates(unit_ids: list[str]) -> list[Candidate]:
    units = by_id()
    return [Candidate(unit=units[u], decision="admit") for u in unit_ids]


def test_echoes_fold_but_their_sources_survive():
    group = _candidates(["mb-method-earn", "mb-echo-baseline-1",
                         "mb-echo-baseline-2"])
    items, operations = coalesce(group)
    assert len(items) == 1
    item = items[0]
    assert set(item.members) == {"mb-method-earn", "mb-echo-baseline-1",
                                 "mb-echo-baseline-2"}
    units = by_id()
    for member in item.members:
        for ref in units[member].source_refs:
            assert ref in item.source_refs
    assert operations[0]["echo_folded"]


def test_disagreement_is_never_coalesced_away():
    group = _candidates(["mb-ch09-result", "mb-refutes-ch9-scope"])
    items, operations = coalesce(group)
    assert len(items) == 2
    dissent = [i for i in items if i.conflict_with]
    assert dissent and dissent[0].members == ("mb-refutes-ch9-scope",)
    assert any(op["operation"] == "preserve_disagreement" for op in operations)


def test_superseded_members_become_a_temporal_note_not_silence():
    group = _candidates(["mb-impl-postgres", "mb-stale-sqlite"])
    items, _ = coalesce(group)
    assert len(items) == 1
    assert "superseded" in items[0].temporal_note
    assert "mb-stale-sqlite" in items[0].members


def test_every_bundle_item_keeps_at_least_one_source(harness):
    for task in fx.all_tasks():
        bundle, _ = harness.build("C6", task)
        for item in bundle.items:
            assert item.source_refs, (task.task_id, item.item_id)


# --------------------------------------------------------------------------
# Metrics and attribution
# --------------------------------------------------------------------------

def test_oracle_condition_is_an_attainable_ceiling(harness):
    for task in fx.all_tasks():
        scored, _, _ = harness.score("CO", task)
        assert scored["must_include_recall"] == 1.0
        assert scored["context_precision"] == 1.0


def test_failure_attribution_names_a_stage(harness):
    task = fx.T7_RELEASE()
    _, bundle, trace = harness.score("C0", task)
    attribution = M.attribute_failure(task, bundle, trace)
    assert attribution["codes"]
    assert set(attribution["codes"]) <= set(M.E_CODES)


def test_conditions_are_declared_not_improvised():
    assert set(CONDITIONS) == {c.name for c in LADDER} | {"CO"}


# --------------------------------------------------------------------------
# Backtesting
# --------------------------------------------------------------------------

def test_backtest_reports_a_decision_for_every_proposal(harness):
    result = backtest(harness, fx.PF_MEMORY_BOOK())
    assert result["proposals"]
    for proposal in result["proposals"]:
        assert proposal["decision"] in ("PROMOTE", "REJECT")
        assert proposal["rationale"]
    assert set(result["promoted"]) & set(result["rejected"]) == set()


def test_a_proposal_that_lowers_the_primary_metric_is_rejected(harness):
    result = backtest(harness, fx.PF_MEMORY_BOOK())
    for proposal in result["proposals"]:
        if proposal["primary_delta"] <= 0:
            assert proposal["decision"] == "REJECT"
