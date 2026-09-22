"""Memory Measurement Instrument v0.1.

The apparatus used to measure memory systems — not a memory system itself.
Implements the contract described in Chapter 2 ("The Measurement Instrument")
and specified normatively in ``spec/benchmark-v0.1.md``.

Status: implemented, experiment pending. No frozen runs exist yet; nothing
in this package reports a book result.
"""

from ._version import __version__
from .tasks import HistoryItem, MemoryTask, SystemOutput
from .observations import FailureClass, MemoryObservation
from .scorers import score_task
from .manifests import RunManifest
from .reports import render_scorecard

__all__ = [
    "HistoryItem",
    "MemoryTask",
    "SystemOutput",
    "FailureClass",
    "MemoryObservation",
    "score_task",
    "RunManifest",
    "render_scorecard",
]
