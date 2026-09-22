"""What counts as a good routing decision.

A router cannot be judged on answer quality alone: a policy that invokes
every mechanism on every query would score well on quality and be
useless. Nor can it be judged on cost alone. So the chapter reports the
raw dimensions first and only then, for the parts of the analysis that
need an ordering (the oracle, regret), applies an explicitly versioned
scalar.

The weights below are a stated choice, not a discovered truth. They are
recorded in every run manifest and the sensitivity of the chapter's
conclusions to them is reported, because a result that survives only at
one setting of lambda is not a result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Quality is the mean of the instrument's task-level metrics for a cell.
# Which metrics those are depends on the task; the instrument decides,
# and this module never invents a scorer.
QUALITY_METRICS = (
    "decision_exactness",
    "current_state_accuracy",
    "historical_state_accuracy",
    "supersession_correctness",
    "abstention_correctness",
)
EVIDENCE_METRICS = ("source_recall", "source_precision")
HARM_METRICS = ("unsupported_source_rate",)


@dataclass(frozen=True)
class UtilityWeights:
    """Versioned trade-off between the dimensions."""

    version: str = "nexus-utility-v0.1"
    quality_weight: float = 1.0
    evidence_weight: float = 0.5
    lambda_cost: float = 0.01
    lambda_latency: float = 0.0
    lambda_harm: float = 0.5
    # Quality threshold for the "cheapest adequate" oracle and for the
    # sequential controller's stop rule.
    adequacy_threshold: float = 0.75

    def to_dict(self) -> dict:
        return asdict(self)


class Utility:
    """Scores one measured matrix cell."""

    def __init__(self, weights: UtilityWeights | None = None) -> None:
        self.weights = weights or UtilityWeights()

    # -- dimensions, each reported raw ------------------------------------

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def quality(self, cell) -> float:
        """Task-level correctness, from the instrument's own metrics."""
        values = [
            cell.metrics[name]
            for name in QUALITY_METRICS
            if name in cell.metrics and cell.metrics[name] is not None
        ]
        return self._mean(values)

    def evidence(self, cell) -> float:
        """Memory-level quality: did the right evidence come back?"""
        values = [
            cell.metrics[name]
            for name in EVIDENCE_METRICS
            if name in cell.metrics and cell.metrics[name] is not None
        ]
        return self._mean(values)

    def harm(self, cell) -> float:
        values = [
            cell.metrics[name]
            for name in HARM_METRICS
            if name in cell.metrics and cell.metrics[name] is not None
        ]
        return self._mean(values)

    # -- the scalar, used only where an ordering is required ---------------

    def score(self, cell) -> float:
        weights = self.weights
        return (
            weights.quality_weight * self.quality(cell)
            + weights.evidence_weight * self.evidence(cell)
            - weights.lambda_cost * cell.cost_units
            - weights.lambda_latency * (cell.latency_ms / 1000.0)
            - weights.lambda_harm * self.harm(cell)
        )

    def dimensions(self, cell) -> dict:
        """Everything, unaggregated. This is what the chapter reports."""
        return {
            "quality": round(self.quality(cell), 4),
            "evidence": round(self.evidence(cell), 4),
            "harm": round(self.harm(cell), 4),
            "cost_units": cell.cost_units,
            "latency_ms": round(cell.latency_ms, 1),
            "context_tokens": cell.context_tokens,
            "model_calls": cell.model_calls,
            "utility": round(self.score(cell), 4),
        }
