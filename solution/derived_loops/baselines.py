"""Conditions: what proposes a candidate determines the recall ceiling.

  unconstrained  every proposed difference is listed (no filter)
  staged         the S0-S4 triple gate
  no-current     gate without the freshness leg (ablation)
  no-expected    gate without the stated-expectation leg (ablation)
  no-cancel      gate without the cancelling-evidence leg (ablation)
  oracle         exactly the ledger-genuine set (ceiling, not a system)
  abstain        silence on every task (trivial control)

Proposal and filtering are measured separately: the gate can only
admit what proposal surfaced, and the unconstrained baseline shows
what listing without a licence costs.
"""

from __future__ import annotations

from . import fixtures as fx
from .gate import apply_gate
from .model import GateDecision, ScopeTask

CONDITIONS = ("unconstrained", "staged", "no-current", "no-expected",
              "no-cancel", "oracle", "abstain")


def run_condition(condition: str,
                  task: ScopeTask) -> list[GateDecision]:
    if condition == "unconstrained":
        return [GateDecision(c.candidate_id, True, None,
                             "listed without a licence",
                             ((c.current.artifact_id,)
                              if c.current else ()))
                for c in task.candidates]
    if condition == "staged":
        return apply_gate(task)
    if condition == "no-current":
        return apply_gate(task, skip_current=True)
    if condition == "no-expected":
        return apply_gate(task, skip_expected=True)
    if condition == "no-cancel":
        return apply_gate(task, skip_cancelling=True)
    if condition == "oracle":
        genuine = fx.ledger_genuine(task)
        return [GateDecision(
            c.candidate_id, c.candidate_id in genuine,
            None if c.candidate_id in genuine else "ORACLE",
            "ledger ceiling" if c.candidate_id in genuine
            else "not ledger-genuine",
            ((c.current.artifact_id,) if c.current else ()))
            for c in task.candidates]
    if condition == "abstain":
        return [GateDecision(c.candidate_id, False, "ABSTAIN",
                             "trivial always-abstain control", ())
                for c in task.candidates]
    raise ValueError(f"unknown condition {condition!r}")
