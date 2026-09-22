"""Single capstone trace connecting retained history to present behaviour."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class CapstoneTrace:
    task_id: str
    condition: str
    bcode: str
    history_id: str
    reader_id: str
    budget_tokens: int
    retrieved: list[str] = field(default_factory=list)
    derived_consulted: list[str] = field(default_factory=list)
    temporal_decisions: list[dict] = field(default_factory=list)
    trust_decisions: list[dict] = field(default_factory=list)
    frame_decision: dict = field(default_factory=dict)
    selected: list[str] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    context_tokens: int = 0
    context_hash: str = ""
    reader_output: dict = field(default_factory=dict)
    behavioural_score: float | None = None
    harm: bool = False
    fallback_events: list[dict] = field(default_factory=list)
    conditional_invocations: list[dict] = field(default_factory=list)

    def why_admitted(self, unit_id: str) -> str | None:
        for entry in self.trust_decisions:
            if entry.get("unit_id") == unit_id:
                return entry.get("reason")
        return None

    def why_rejected(self, unit_id: str) -> str | None:
        for entry in self.rejected:
            if entry.get("unit_id") == unit_id:
                return entry.get("reason")
        return None

    def to_dict(self) -> dict:
        return asdict(self)
