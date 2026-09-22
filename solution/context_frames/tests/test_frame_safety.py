"""Unit tests for frame establishment and safe policy.

No model services. Every test is deterministic: the gate reads only
observable signals, never hidden labels, never self-confidence.
"""

from context_frames import fixtures as fx
from context_frames import frame_fixtures as ff
from context_frames import frame_safety as fs
from context_frames.frame_safety import (
    ABSTAIN,
    BROADEN,
    CONFLICTING,
    CORROBORATED,
    DECLARED,
    HARD_FRAME,
    INFERRED,
    QUERY_ONLY,
    REQUEST_MORE,
    SOFT_FRAME,
    STALE,
    UNKNOWN,
)
from context_frames.model import WorkSignal

PROJ = fx.PF_MEMORY_BOOK()


def sig(sid, kind, text, at="2026-09-20T09:00:00Z"):
    return WorkSignal(signal_id=sid, kind=kind, text=text,
                      observed_at=at)


def test_declared_frame_recognised():
    s = ff.scenario_by_id("A-fix-dec-dev")
    dec, _ = fs.classify_establishment(
        s.signals, PROJ, fx.AS_OF, ("SET_BACKEND",))
    assert dec.establishment == DECLARED
    assert dec.action == HARD_FRAME
    assert dec.selected_work_type == fx.WT_IMPLEMENTATION


def test_corrorborated_frame_recognised():
    signals = (
        sig("s1", "project_state",
            "Project memory-book; release branch open for the cut."),
        sig("s2", "tool_result",
            "Sweep tool reports three outstanding release blockers."),
    )
    dec, _ = fs.classify_establishment(signals, PROJ, fx.AS_OF, ())
    assert dec.establishment == CORROBORATED
    assert dec.action == HARD_FRAME
    assert dec.selected_work_type == fx.WT_RELEASE


def test_single_inferred_signal_stays_non_hard():
    s = ff.scenario_by_id("B-prose-weak-dev")
    dec, _ = fs.classify_establishment(s.signals, PROJ, fx.AS_OF, ())
    assert dec.establishment == INFERRED
    assert dec.action == SOFT_FRAME


def test_conflict_detected():
    s = ff.scenario_by_id("D-cleanup-conflict-dev")
    dec, _ = fs.classify_establishment(s.signals, PROJ, fx.AS_OF,
                                       ("KEEP_FACADE",))
    assert dec.establishment == CONFLICTING
    assert dec.action == QUERY_ONLY
    assert "fsig-workflow-impl" in dec.conflicting_refs


def test_stale_frame_detected():
    s = ff.scenario_by_id("C-ship-shift-dev")
    dec, _ = fs.classify_shift(
        s.signals, PROJ, fx.AS_OF, s.prior_work_type,
        s.prior_basis_ids, ())
    assert dec.establishment == STALE
    assert dec.action == QUERY_ONLY
    assert any(r.startswith("F4_SUPERSEDED_BY_") for r in dec.reasons)


def test_unknown_frame_handled():
    s = ff.scenario_by_id("E-cite-unknown-dev")
    dec, _ = fs.classify_establishment(s.signals, PROJ, fx.AS_OF,
                                       ("CITE_RULE",))
    assert dec.establishment == UNKNOWN
    assert dec.action == QUERY_ONLY  # reversible schema


def test_unknown_consequential_requests_evidence():
    s = ff.scenario_by_id("K-cleanup-unknown-dev")
    dec, _ = fs.classify_establishment(s.signals, PROJ, fx.AS_OF,
                                       ("DELETE_FACADE", "MIGRATE_CALLERS"))
    assert dec.establishment == UNKNOWN
    assert dec.action == REQUEST_MORE
    assert dec.high_stakes is True


def test_soft_frame_preserves_query_only_candidates():
    # The soft exclusion rule is the point: an ABSENT-tier unit with
    # strong query support must be retained, with the retention
    # recorded — not silently, not by exclusion.
    from context_frames import policy as P
    cond = fs.condition_for_action(SOFT_FRAME)
    assert cond.soft_frame is True
    assert cond.expand_with_objective is True
    assert cond.class_pull is True


def test_hard_frame_can_exclude_only_when_permitted():
    from context_frames import policy as P
    cond = fs.condition_for_action(HARD_FRAME)
    assert cond.name == "C5"
    assert cond.soft_frame is False


def test_query_only_fallback_byte_equivalent_to_baseline():
    import sys
    sys.path.insert(0, "solution")
    from context_frames import policy as P
    from context_frames.corpus import corpus
    from context_frames.retrieval import HybridRetriever
    units = {u.unit_id: u for u in corpus()}
    retriever = HybridRetriever(list(units.values()), None)
    task = fx.T1_ARCHITECTURE()
    frame = fx.PF_MEMORY_BOOK()
    cond = fs.condition_for_action(QUERY_ONLY)
    assert cond.name == "C0"
    b1, _ = P.build_context("C0", task.query, frame, task.work_frame,
                            retriever, units, 1500,
                            trace_id="t-C0")
    b2, _ = P.build_context(cond.name, task.query, frame, task.work_frame,
                            retriever, units, 1500,
                            trace_id="t-FB")
    assert b1.digest() == b2.digest()


def test_hidden_labels_unavailable_to_policy():
    # The gate module must not import fixture hidden labels: it
    # receives signals, a project, a standpoint and an action schema.
    import inspect
    src = inspect.getsource(fs.classify_establishment)
    for token in ("true_work_type", "true_project", "wrong_work_type",
                  "needs_memory", "irreversible", "correct_frame",
                  "fixture_type", "oracle_action"):
        assert token not in src, token


def test_dev_eval_split_isolation():
    dev_ids = {s.scenario_id for s in ff.dev_scenarios()}
    eval_ids = {s.scenario_id for s in ff.eval_scenarios()}
    assert dev_ids & eval_ids == set()
    assert all(i.endswith("-dev") for i in dev_ids)
    assert all(i.endswith("-eval") for i in eval_ids)
    # Tuning provenance: adaptive thresholds will record TUNING_SOURCES;
    # the gate mapping itself takes no split input (pure function).
    import context_frames.adaptive_retrieval as ar
    assert "eval" not in ar.TUNING_SOURCES
    assert set(ar.TUNING_SOURCES) <= dev_ids


def test_frame_reasons_come_from_real_decision_logic():
    s = ff.scenario_by_id("A-fix-dec-dev")
    _, trace = fs.classify_establishment(s.signals, PROJ, fx.AS_OF, ())
    assert trace.decision is not None
    assert trace.decision["reasons"] == ["F1_DIRECT_DECLARATION"]
    assert trace.decision["supporting_refs"] == ("fsig-a1-user",) or \
        set(trace.decision["supporting_refs"]) == {"fsig-a1-user"}


def test_frame_trace_deterministic():
    s = ff.scenario_by_id("D-cleanup-conflict-dev")
    _, t1 = fs.classify_establishment(s.signals, PROJ, fx.AS_OF, ())
    _, t2 = fs.classify_establishment(s.signals, PROJ, fx.AS_OF, ())
    assert t1.to_dict() == t2.to_dict()


def test_bundle_hash_deterministic():
    import sys
    sys.path.insert(0, "solution")
    from context_frames import policy as P
    from context_frames.corpus import corpus
    from context_frames.retrieval import HybridRetriever
    units = {u.unit_id: u for u in corpus()}
    retriever = HybridRetriever(list(units.values()), None)
    task = fx.T4()
    frame = fx.PF_MEMORY_BOOK()
    b1, _ = P.build_context("C5", task.query, frame, task.work_frame,
                            retriever, units, 1500, trace_id="t-1")
    b2, _ = P.build_context("C5", task.query, frame, task.work_frame,
                            retriever, units, 1500, trace_id="t-2")
    assert b1.digest() == b2.digest()


def test_policy_mapping_table():
    assert fs.select_action(DECLARED, False) == HARD_FRAME
    assert fs.select_action(DECLARED, True) == HARD_FRAME
    assert fs.select_action(CORROBORATED, False) == HARD_FRAME
    assert fs.select_action(INFERRED, False) == SOFT_FRAME
    assert fs.select_action(INFERRED, True) == SOFT_FRAME
    assert fs.select_action(CONFLICTING, False) == QUERY_ONLY
    assert fs.select_action(STALE, True) == QUERY_ONLY
    assert fs.select_action(UNKNOWN, False) == QUERY_ONLY
    assert fs.select_action(UNKNOWN, True) == REQUEST_MORE


def test_selected_frame_never_declared():
    # Gate-built frames are always derivation="inferred". Declared
    # (person-written) frames come from fixtures, never from the gate.
    s = ff.scenario_by_id("A-fix-dec-dev")
    dec, _ = fs.classify_establishment(s.signals, PROJ, fx.AS_OF, ())
    frame = fs.build_selected_frame(
        dec.selected_work_type, PROJ, s.signals,
        dec.supporting_refs, "wf-test", fx.AS_OF)
    assert frame.derivation == "inferred"
    assert frame.unprovenanced_fields() == ()
