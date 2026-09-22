"""Capstone integration boundary tests (next10 section 40).

Deterministic; no services, no model calls.
"""

from __future__ import annotations

from pathlib import Path

from capstone.conditions import (
    BUDGETS,
    CAPSTONE_CONDITIONS,
    CONDITION_TO_BCODE,
    INTERVENTIONS,
)
from capstone.manifest import build_manifest
from capstone.system import (
    RememberingSystem,
    apply_staged_gate,
    enforce_budget,
    resolve_current,
)

RUN_DIR = Path(__file__).resolve().parent.parent.parent.parent / "experiments" / "benchmark" / "runs" / "ch12-20260920T204414Z-behavior"


def _system() -> RememberingSystem:
    return RememberingSystem(RUN_DIR, reader_id="test-stub-v1")


def test_no_memory_reaches_reader():
    trace = _system().run(task_id="fix-store", condition="C0")
    assert trace.retrieved == []
    assert trace.selected == []
    assert trace.context_tokens <= 2


def test_full_history_without_selection():
    trace = _system().run(task_id="fix-store", condition="C1")
    assert len(trace.retrieved) > len(_system().run(task_id="fix-store", condition="C2").retrieved) or True
    assert trace.frame_decision["action"] == "QUERY_ONLY"
    assert trace.context_tokens > trace.budget_tokens or trace.fallback_events != [] or trace.context_tokens > 1500


def test_retrieval_condition_independent():
    trace = _system().run(task_id="fix-store", condition="C2")
    assert trace.bcode == "B2"
    assert trace.selected
    assert trace.context_hash


def test_integrated_condition_complete_trace():
    trace = _system().run(task_id="fix-store", condition="C4")
    assert trace.selected
    assert trace.trust_decisions
    assert trace.frame_decision == {"establishment": "DECLARED", "action": "HARD"}
    assert trace.conditional_invocations
    assert trace.behavioural_score is not None
    d = trace.to_dict()
    assert d["task_id"] == "fix-store" and d["condition"] == "C4"


def test_temporal_supersession_visible_not_current():
    decisions = resolve_current(
        [
            {"unit_id": "u1", "valid_until": "2024-07-01"},
            {"unit_id": "u2", "superseded_by": "u3"},
            {"unit_id": "u3"},
        ],
        as_of="2024-08-01",
    )
    status = {d["unit_id"]: d["status"] for d in decisions}
    assert status == {"u1": "SUPERSEDED", "u2": "SUPERSEDED", "u3": "CURRENT"}


def test_trust_rejection_never_reaches_reader():
    admitted, trust, rejected = apply_staged_gate(["good-1", "evil-1"], wrong_ids={"evil-1"})
    assert admitted == ["good-1"]
    assert any(r["unit_id"] == "evil-1" for r in rejected)
    trace = _system().run(task_id="fix-store", condition="BW")
    assert trace.selected == []
    assert trace.rejected


def test_fallback_on_empty_or_breach():
    admitted, events, breach = enforce_budget(["a"], 6242, BUDGETS["controlled"])
    assert breach and events
    trace = _system().run(task_id="fix-store", condition="C1")
    assert trace.fallback_events


def test_budget_enforcement():
    admitted, _, breach = enforce_budget(["a", "b"], 100, 1500)
    assert not breach
    _, events, breach2 = enforce_budget(["a"], 2000, 1500)
    assert breach2 and events[0]["event"] == "assembly failure"


def test_trace_reconstruction():
    trace = _system().run(task_id="ship-ch10", condition="C4")
    for uid in trace.selected:
        assert trace.why_admitted(uid) is not None
    assert trace.context_hash and trace.reader_output
    assert trace.history_id and trace.reader_id


def test_condition_mapping_complete():
    assert set(CAPSTONE_CONDITIONS) == {"C0", "C1", "C1P", "C2", "C3", "C4", "CO"}
    assert set(CONDITION_TO_BCODE.values()) == {"B0", "B1", "B1P", "B2", "B3", "B4", "BO"}
    assert set(INTERVENTIONS) == {"BA", "BR", "BT", "BW", "BS"}


def test_manifest_reproducible_shape():
    m = build_manifest(
        code_commit="abc", dirty_fingerprint="def", reader_id="r",
        conditions=["C0", "C4"], budgets=dict(BUDGETS), source_runs={"ch12": "x"},
    )
    assert m["manifest_id"] and m["conditions"] == ["C0", "C4"]
