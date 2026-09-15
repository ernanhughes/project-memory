"""Schema validation tests (H1 pipeline stage 1)."""

import pytest

from generator.schema import Ledger, LedgerError, Record


def _rec(**kw):
    base = dict(
        key="r1", kind="decision", topic="t", content="Decide X.",
        date="2024-07-11", valid_from="2024-07-11", display_id="adr-100",
        artifact_kind="adr", scenario="discussion_decision",
    )
    base.update(kw)
    return Record(**base)


def test_valid_ledger_passes():
    ledger = Ledger([
        _rec(key="a", display_id="adr-100"),
        _rec(key="b", kind="evidence", display_id="session-101",
             artifact_kind="session", scenario="discussion_decision",
             supported_by=("a",)),
    ]).validate()
    assert len(ledger.records) == 2


def test_bad_kind_rejected():
    with pytest.raises(LedgerError):
        Ledger([_rec(kind="hunch")]).validate()


def test_bad_date_rejected():
    with pytest.raises(LedgerError):
        Ledger([_rec(date="July 11")]).validate()


def test_dangling_reference_rejected():
    with pytest.raises(LedgerError):
        Ledger([_rec(supported_by=("ghost",))]).validate()


def test_derived_cycle_rejected():
    with pytest.raises(LedgerError):
        Ledger([
            _rec(key="a", kind="derived_restatement", display_id="runbook-100",
                 artifact_kind="runbook", scenario="derived_restatement",
                 derived_from=("b",)),
            _rec(key="b", kind="derived_restatement", display_id="runbook-101",
                 artifact_kind="runbook", scenario="derived_restatement",
                 derived_from=("a",)),
        ]).validate()


def test_suffix_collision_rejected():
    with pytest.raises(LedgerError):
        Ledger([
            _rec(key="a", display_id="adr-100"),
            _rec(key="b", display_id="session-100"),
        ]).validate()


def test_split_without_second_id_rejected():
    with pytest.raises(LedgerError):
        Ledger([_rec(render_style="split")]).validate()


def test_missing_scenario_rejected():
    import dataclasses
    rec2 = dataclasses.replace(_rec(), scenario="")
    with pytest.raises(LedgerError):
        Ledger([rec2]).validate()
