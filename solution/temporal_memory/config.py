"""Configuration for the temporal-memory package."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TemporalConfig:
    """Runtime configuration. ZeroMQ-free defaults; transport chosen later."""

    projection_version: str = "temporal-projection-v0.1"
    fixture_version: str = "e8-fixture-v0.1"
    # Standpoint default: project standpoint (agent/task standpoints deferred).
    standpoint: str = "project"
    # Transport knobs (baseline avoids sleep-based correctness).
    zmq_ready_timeout_s: float = 10.0
    zmq_poll_timeout_ms: int = 2000

    def to_dict(self) -> dict:
        return {
            "projection_version": self.projection_version,
            "fixture_version": self.fixture_version,
            "standpoint": self.standpoint,
            "zmq_ready_timeout_s": self.zmq_ready_timeout_s,
            "zmq_poll_timeout_ms": self.zmq_poll_timeout_ms,
        }
