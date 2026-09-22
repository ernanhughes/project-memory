"""Task representation for the Measurement Instrument.

A task fixes what the system is asked, what history it may see, and what
the hidden ledger says the correct answer is. The system under test never
receives the expected fields — only the prompt and the rendered history.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ANSWERABLE = "answerable"
UNANSWERABLE = "unanswerable"

# Task families follow the book's six questions.
LOCATE = "locate"  # Q1: where was X discussed?
DECISION = "decision"  # Q2: what was decided?
PROVENANCE = "provenance"  # Q3: why was it decided?
TEMPORAL = "temporal"  # Q4: is it still true?
OPEN_LOOP = "open-loop"  # Q5: what was left unfinished?
USE = "use"  # Q6: what from the past matters right now?


@dataclass(frozen=True)
class HistoryItem:
    """One rendered artifact the system under test may see."""

    item_id: str
    text: str
    kind: str = "record"
    timestamp: str | None = None


@dataclass(frozen=True)
class MemoryTask:
    """A single measurement task with hidden ground truth.

    ``expected_*`` fields are evaluator ground truth derived from the
    ledger. They must never be shown to the system under test.
    """

    task_id: str
    family: str
    prompt: str
    history_ref: str
    expected_sources: tuple[str, ...] = ()
    expected_state: str | None = None
    expected_aliases: tuple[str, ...] = ()
    expected_status: str = ANSWERABLE
    temporal_mode: str | None = None  # None | "current" | "historical"
    expected_current: str | None = None
    expected_historical: str | None = None
    superseded_options: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if self.expected_status not in (ANSWERABLE, UNANSWERABLE):
            raise ValueError(f"unknown expected_status: {self.expected_status}")
        if self.temporal_mode not in (None, "current", "historical"):
            raise ValueError(f"unknown temporal_mode: {self.temporal_mode}")


@dataclass(frozen=True)
class SystemOutput:
    """What a system under test produced for one task."""

    task_id: str
    answer: str | None = None
    cited_sources: tuple[str, ...] = ()
    retrieved_ids: tuple[str, ...] = ()
    abstained: bool = False
    context_tokens: int | None = None
    notes: str = ""
