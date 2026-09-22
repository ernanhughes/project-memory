"""Derived loops: inference as a liability.

A derived loop is a concluded debt nobody stated, admissible only with
a (current, expected, difference) triple. Every leg carries provenance;
every rejection carries a reason-coded stage. No scalar confidence, no
LLM explanation after the fact.
"""

from .model import (
    GATE_VERSION,
    DerivedCandidate,
    GateDecision,
    Leg,
    ScopeTask,
)
from .gate import apply_gate
from .fixtures import all_tasks, ledger_genuine
from .baselines import run_condition

__all__ = [
    "GATE_VERSION",
    "DerivedCandidate",
    "GateDecision",
    "Leg",
    "ScopeTask",
    "apply_gate",
    "all_tasks",
    "ledger_genuine",
    "run_condition",
]
