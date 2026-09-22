"""Open loops (Chapter 9): expected transitions and evidence of absence.

Chapter 8 remembers transitions that happened. This layer remembers
transitions that were expected to happen but have not yet happened.

An open loop is an established expectation about a future state
transition for which no satisfactory closing transition has yet been
observed. Status is resolved against Chapter 8's ordered history; it is
never a keyword search over mentions.
"""

from .model import (EXPECTATION_SCHEMA_VERSION, ExpectedTransition,
                    Expectation, SearchFootprint, StatusReport)
from .status import STATUS, resolve_status

__all__ = [
    "EXPECTATION_SCHEMA_VERSION",
    "ExpectedTransition",
    "Expectation",
    "SearchFootprint",
    "StatusReport",
    "STATUS",
    "resolve_status",
]
