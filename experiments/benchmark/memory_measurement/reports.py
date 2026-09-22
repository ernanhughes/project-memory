"""Human-readable scorecards for measurement runs.

Per-question results come first; no aggregate is computed here. Fields
the v0.1 implementation cannot yet produce are labelled pending rather
than filled with plausible numbers.
"""

from __future__ import annotations

from .manifests import RunManifest
from .observations import MemoryObservation

PENDING = "pending"

# Rate metrics where lower values are better. The scorecard marks them so
# that readers do not mistake a low fabrication rate for a low score.
LOWER_IS_BETTER: tuple[str, ...] = ("unsupported_source_rate",)

# Metrics v0.1 does not yet implement. Listed explicitly so that the
# scorecard cannot silently pretend to measure them.
PENDING_METRICS: tuple[str, ...] = (
    "ranking.MRR",
    "ranking.nDCG",
    "provenance.support_chain_validity",
    "temporal.validity_interval_accuracy",
    "temporal.unresolved_conflict_calibration",
    "epistemic.promotion_error_rate",
    "behaviour.memory_changed_action",
    "behaviour.memory_improved_action",
    "behaviour.harmful_memory_rate",
    "cost.retrieved_tokens",
    "cost.context_tokens",
    "cost.model_calls",
)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _format(value: float | bool | str | None) -> str:
    if value is None:
        return PENDING
    if isinstance(value, bool):
        return "1.00" if value else "0.00"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def render_scorecard(
    observations: list[MemoryObservation],
    manifest: RunManifest,
    family_of: dict[str, str] | None = None,
) -> str:
    """Render per-metric means grouped by task family."""
    family_of = family_of or {}
    by_metric: dict[str, list[float]] = {}
    for observation in observations:
        if isinstance(observation.value, (bool, float)):
            by_metric.setdefault(observation.metric, []).append(
                1.0 if observation.value is True else 0.0
                if observation.value is False
                else observation.value
            )
    failures = [
        f"{o.task_id}:{o.failure_class}"
        for o in observations
        if o.failure_class is not None
    ]
    lines = [
        "Memory Measurement Run",
        "======================",
        "",
        f"System:    {manifest.system_name}",
        f"Condition: {manifest.condition}",
        f"Corpus:    {manifest.corpus_version}",
        f"Tasks:     {manifest.task_set_version}",
        f"Run:       {manifest.run_id} (manifest {manifest.manifest_hash})",
        "",
    ]
    for metric in sorted(by_metric):
        mean = _mean(by_metric[metric])
        marker = "  (lower is better)" if metric in LOWER_IS_BETTER else ""
        lines.append(f"  {_format(mean):>8}  {metric}{marker}")
    lines.append("")
    for pending in PENDING_METRICS:
        lines.append(f"  {PENDING:>8}  {pending}")
    lines.append("")
    if failures:
        lines.append("Failure attribution")
        for item in sorted(set(failures)):
            lines.append(f"  {item}")
    else:
        lines.append("No failures attributed.")
    return "\n".join(lines) + "\n"
