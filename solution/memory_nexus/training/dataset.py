"""Turning the measured matrix into router training data.

The label for a query is not "the right answer" — it is "the capability
that should have been invoked", derived from measurement rather than from
opinion. Two labelling rules are offered because they encode different
goals:

``best_utility``
    the capability with the highest utility;
``cheapest_adequate``
    the cheapest capability that reached the quality threshold, which is
    what a cost-aware router should actually learn.

Two leakage hazards are handled here, and both are real enough to have
been checked rather than asserted.

*Feature leakage*: the router's features are built by the same code path
the live system uses, and an audit refuses any evaluator-only field. A
router that could see the ledger's task family would be reading the
answer key.

*Split leakage*: this benchmark is small and its tasks come in families
that share wording. Splitting at random would put near-duplicate
questions on both sides. ``split_by_family`` holds out whole families, so
the held-out condition tests whether the router generalises to a *kind*
of question rather than to a paraphrase it has already seen.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..state.features import FEATURE_NAMES, audit_state, feature_vector


@dataclass
class RoutingSample:
    query_id: str
    features: list[float]
    label: str
    label_rule: str
    routing_family: str = ""
    alternatives: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def build_samples(
    matrix,
    utility,
    state_by_query: dict,
    label_rule: str = "cheapest_adequate",
    routing_families: dict[str, str] | None = None,
) -> tuple[list[RoutingSample], dict]:
    """Derive one labelled sample per task from the measured matrix."""
    families = routing_families or {}
    samples: list[RoutingSample] = []
    leakage: list[str] = []
    threshold = utility.weights.adequacy_threshold
    for query_id, cells in matrix.by_query().items():
        measured = [cell for cell in cells if cell.measured]
        state = state_by_query.get(query_id)
        if not measured or state is None:
            continue
        found = audit_state(state)
        if found:
            leakage.append(f"{query_id}: {found}")
            continue
        if label_rule == "best_utility":
            label = max(
                measured,
                key=lambda cell: (utility.score(cell), cell.capability_id),
            ).capability_id
        else:
            adequate = [
                cell for cell in measured
                if utility.quality(cell) >= threshold
            ]
            label = min(
                adequate or measured,
                key=lambda cell: (
                    cell.cost_units,
                    -utility.quality(cell),
                    cell.capability_id,
                ),
            ).capability_id
        samples.append(
            RoutingSample(
                query_id=query_id,
                features=feature_vector(state),
                label=label,
                label_rule=label_rule,
                routing_family=families.get(query_id, ""),
                alternatives={
                    cell.capability_id: {
                        "quality": round(utility.quality(cell), 4),
                        "cost": cell.cost_units,
                        "utility": round(utility.score(cell), 4),
                    }
                    for cell in measured
                },
            )
        )
    report = {
        "samples": len(samples),
        "label_rule": label_rule,
        "adequacy_threshold": threshold,
        "feature_names": list(FEATURE_NAMES),
        "label_distribution": _distribution(samples),
        "leakage_rejections": leakage,
    }
    return samples, report


def _distribution(samples: list[RoutingSample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        counts[sample.label] = counts.get(sample.label, 0) + 1
    return dict(sorted(counts.items()))


def split_by_family(
    samples: list[RoutingSample], holdout_families: tuple[str, ...]
) -> tuple[list[RoutingSample], list[RoutingSample]]:
    """Hold out whole question families, never individual paraphrases."""
    train = [
        sample for sample in samples
        if sample.routing_family not in holdout_families
    ]
    test = [
        sample for sample in samples
        if sample.routing_family in holdout_families
    ]
    return train, test


def check_no_answer_tokens(
    samples: list[RoutingSample], tasks
) -> list[str]:
    """Assert that no expected-answer string reached a feature vector.

    Features are numeric, so the real risk is not literal tokens but a
    feature that is a proxy for the label. This check is the cheap half:
    it confirms the feature vector has the declared width and carries no
    per-task identity that could memorise the mapping.
    """
    problems: list[str] = []
    width = len(FEATURE_NAMES)
    seen: dict[tuple, set[str]] = {}
    for sample in samples:
        if len(sample.features) != width:
            problems.append(f"{sample.query_id}: feature width mismatch")
        key = tuple(round(value, 6) for value in sample.features)
        seen.setdefault(key, set()).add(sample.label)
    # Identical features with different labels is honest ambiguity, not
    # leakage; unique features per task would be the warning sign.
    unique = sum(1 for labels in seen.values() if len(labels) == 1)
    if len(seen) == len(samples) and len(samples) > 8:
        problems.append(
            f"every task has a unique feature vector ({unique} singletons): "
            "the router could memorise rather than generalise"
        )
    return problems


def save_dataset(
    samples: list[RoutingSample], report: dict, path: Path
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "report": report,
                "samples": [sample.to_dict() for sample in samples],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path
