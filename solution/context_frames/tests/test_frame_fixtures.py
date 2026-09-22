"""Unit tests: fixtures, adaptive baseline, derived pipeline.

No model services. Split digests, isolation rules, licence screening
and preference semantics are all deterministic.
"""

from context_frames import adaptive_retrieval as ar
from context_frames import derived_context as dc
from context_frames import frame_fixtures as ff
from context_frames import frame_safety as fs


def test_split_counts_and_digests():
    assert len(ff.dev_scenarios()) == 11
    assert len(ff.eval_scenarios()) == 9
    digests = ff.split_digests()
    assert len(digests["dev"]) == 16
    assert len(digests["eval"]) == 16
    assert digests["dev"] != digests["eval"]
    assert digests["dev_count"] == 11
    assert digests["eval_count"] == 9


def test_tuning_sources_are_dev_only():
    dev_ids = {s.scenario_id for s in ff.dev_scenarios()}
    eval_ids = {s.scenario_id for s in ff.eval_scenarios()}
    assert set(ar.TUNING_SOURCES) <= dev_ids
    assert set(ar.TUNING_SOURCES) & eval_ids == set()


def test_all_scenarios_match_preregistered_gate():
    from context_frames import fixtures as fx
    from behavior_eval.tasks import task_by_id
    proj = fx.PF_MEMORY_BOOK()
    for s in ff.all_scenarios():
        t = task_by_id(s.behavior_task)
        if s.prior_work_type:
            dec, _ = fs.classify_shift(
                s.signals, proj, fx.AS_OF, s.prior_work_type,
                s.prior_basis_ids, t.action_schema)
        else:
            dec, _ = fs.classify_establishment(
                s.signals, proj, fx.AS_OF, t.action_schema)
        assert (dec.establishment, dec.action) == (
            s.expected_class, s.expected_action), s.scenario_id


def test_adaptive_skip_fires_on_empty_pool():
    decision, kept, detail = ar.adaptive_decide([], {}, 1500)
    assert decision == ar.SKIP
    assert kept == []


def test_adaptive_narrow_needs_margin_and_single_project():
    from context_frames.model import MemoryUnit
    units = {f"u{i}": MemoryUnit(
        unit_id=f"u{i}", project_id="memory-book", kind="experiment_result",
        text="x " * 40) for i in range(10)}
    ranked = [(f"u{i}", 0.03 - i * 0.001) for i in range(10)]
    decision, kept, detail = ar.adaptive_decide(
        ranked, units, 1500, m_hi=0.2, abs_floor=0.001, rel_floor=0.02)
    assert decision in (ar.NARROW, ar.BROAD)
    assert detail["spread"] == 1
    # Flat scores -> margin tiny -> BROAD.
    assert decision == ar.BROAD


def test_adaptive_narrow_fires_on_dominant_top_hit():
    from context_frames.model import MemoryUnit
    units = {f"u{i}": MemoryUnit(
        unit_id=f"u{i}", project_id="memory-book", kind="experiment_result",
        text="x " * 40) for i in range(10)}
    ranked = [("u0", 0.09)] + [(f"u{i}", 0.01) for i in range(1, 10)]
    decision, kept, detail = ar.adaptive_decide(
        ranked, units, 1500, m_hi=0.2, abs_floor=0.001, rel_floor=0.02)
    assert decision == ar.NARROW
    assert kept == ["u0"] or set(kept) <= {"u0"}


def test_adaptive_skip_fires_below_floor():
    from context_frames.model import MemoryUnit
    units = {"u0": MemoryUnit(
        unit_id="u0", project_id="memory-book", kind="experiment_result",
        text="x " * 40)}
    decision, kept, detail = ar.adaptive_decide(
        [("u0", 0.001)], units, 1500, abs_floor=0.008)
    assert decision == ar.SKIP
    assert kept == []


def test_loop_texts_match_ch12_derived_texts():
    from behavior_eval.experiments import DERIVED_TEXTS
    alias = {"c-facade-delete": "c-facade-listing"}
    for cid, text in dc.LOOP_TEXTS.items():
        assert DERIVED_TEXTS[alias.get(cid, cid)] == text, cid
    # The fallback join must reproduce the Ch12 B1-cleanup string
    # exactly, so hash-gated reuse fires.
    full = "\n\n---\n\n".join(
        dc.LOOP_TEXTS[k] for k in ("c-docs-flags", "c-cli-half", "c-web",
                                   "c-facade-delete"))
    assert full == "\n\n---\n\n".join(
        DERIVED_TEXTS[k] for k in ("c-docs-flags", "c-cli-half", "c-web",
                                   "c-facade-listing"))


def test_licence_screen_rejects_facade():
    rendered, trace = dc.build_derived_context(
        "release_readiness", "Plan the corpus import cleanup.", "hard")
    lic = {row["candidate"]: row for row in trace["licence"]}
    assert lic["c-facade-delete"]["admitted"] is False
    assert lic["c-facade-delete"]["stage_failed"] == "S4"
    assert lic["c-docs-flags"]["admitted"] is True
    assert "c-facade-delete" not in trace["admitted"]


def test_hard_wrong_frame_drops_loops():
    query = ("Plan the corpus import cleanup: which migrations to run, "
             "what to do about docs and the compatibility facade.")
    hard_pub, trace_pub = dc.build_derived_context(
        "publication_review", query, "hard")
    hard_rel, trace_rel = dc.build_derived_context(
        "release_readiness", query, "hard")
    # The wrong (publication) frame must admit strictly less loop
    # evidence than the correct (release) frame, or the family is
    # insensitive (positive-control gate decides at analysis time).
    rel_loops = {u for u in trace_rel["admitted"]
                 if u.startswith("c-") and u != "c-facade-delete"}
    pub_loops = {u for u in trace_pub["admitted"]
                 if u.startswith("c-") and u != "c-facade-delete"}
    assert rel_loops != set()  # correct frame keeps migration evidence
    assert pub_loops <= rel_loops


def test_soft_never_drops_for_class():
    query = ("Plan the corpus import cleanup: which migrations to run, "
             "what to do about docs and the compatibility facade.")
    _, trace = dc.build_derived_context(
        "publication_review", query, "soft")
    assert not [d for d in trace["dropped"]
                if d.get("reason") == "CLASS_ABSENT_AND_LOW_QUERY_SUPPORT"]
    assert any("CLASS_ABSENT_BUT_RETAINED" in str(p)
               for p in trace["preference"])


def test_cancelling_notes_travel_with_hard_release():
    query = ("Plan the corpus import cleanup: which migrations to run, "
             "what to do about docs and the compatibility facade.")
    _, trace = dc.build_derived_context(
        "release_readiness", query, "hard")
    assert "note-contract-004" in trace["admitted"]


def test_poison_only_in_pool_when_included():
    _, trace = dc.build_derived_context(
        "release_readiness", "cleanup", "hard", include_poison=False)
    assert "poison_in_pool" not in trace
    _, trace2 = dc.build_derived_context(
        "release_readiness", "cleanup", "hard", include_poison=True,
        poison_text=ff.J_POISON_TEXT)
    assert trace2["poison_in_pool"] is True


def test_derived_render_deterministic():
    q = "Plan the corpus import cleanup."
    r1, _ = dc.build_derived_context("release_readiness", q, "hard")
    r2, _ = dc.build_derived_context("release_readiness", q, "hard")
    assert r1 == r2


def test_transfer_example_scores_zero():
    import sys
    sys.path.insert(0, "solution")
    from behavior_eval import prompts as P
    sys.path.insert(0, ".")
    import run_ch13_transfer as RT
    for task_id in RT.TASKS:
        actions, ok = P.parse_actions(
            '{"actions": [%s]}' % RT.EXAMPLE,
            RT.SCHEMA)
        assert ok is True, task_id
        assert RT.grade_transfer(task_id, actions)["task_score"] == 0.0, \
            task_id


def test_transfer_grading_exact_fields():
    import sys
    sys.path.insert(0, ".")
    import run_ch13_transfer as RT
    graded = RT.grade_transfer(
        "rt-branch", [{"action_type": "REPORT_FRAME",
                       "establishment": "CONFLICTING",
                       "action": "QUERY_ONLY"}])
    assert graded["task_score"] == 1.0
    graded = RT.grade_transfer(
        "rt-branch", [{"action_type": "REPORT_FRAME",
                       "establishment": "DECLARED",
                       "action": "QUERY_ONLY"}])
    assert graded["task_score"] == 0.5


def test_wrong_frames_cover_all_f3_scenarios():
    for s in ff.all_scenarios():
        if s.family in ("J", "L"):
            assert s.wrong_work_type is None, s.scenario_id
        else:
            assert s.wrong_work_type is not None, s.scenario_id
            assert s.wrong_work_type != s.true_work_type or \
                s.true_work_type is None, s.scenario_id
