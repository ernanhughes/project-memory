"""Capstone condition ladder (contract section 7).

C0..C4 + CO reuse the validated B-code design; interventions pass through.
"""

from __future__ import annotations

CAPSTONE_CONDITIONS = ("C0", "C1", "C1P", "C2", "C3", "C4", "CO")

CONDITION_TO_BCODE = {
    "C0": "B0",
    "C1": "B1",
    "C1P": "B1P",
    "C2": "B2",
    "C3": "B3",
    "C4": "B4",
    "CO": "BO",
}

INTERVENTIONS = ("BA", "BR", "BT", "BW", "BS")

BCODE_TO_CAPSTONE = {v: k for k, v in CONDITION_TO_BCODE.items()}

# Hard context budgets (estimated tokens, chars//4) per contract section 9.
BUDGETS = {"controlled": 1500, "assembled": 768}
