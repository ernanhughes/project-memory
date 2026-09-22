"""Configuration for the open-loops package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpenLoopConfig:
    """Runtime configuration; all deterministic, no model calls."""

    expectation_schema_version: str = "open-loop-expectation-v0.1"
    resolver_version: str = "open-loop-resolver-v0.1"
    fixture_version: str = "e9-fixture-v0.1"
    # Semantic-closure token-overlap threshold (measured, not tuned blind).
    semantic_overlap_threshold: float = 0.35
    # Re-verification cadence for the long-running simulation (cycles).
    reverify_every_cycles: int = 3

    def to_dict(self) -> dict:
        return {
            "expectation_schema_version": self.expectation_schema_version,
            "resolver_version": self.resolver_version,
            "fixture_version": self.fixture_version,
            "semantic_overlap_threshold": self.semantic_overlap_threshold,
            "reverify_every_cycles": self.reverify_every_cycles,
        }
