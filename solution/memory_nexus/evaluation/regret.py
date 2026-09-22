"""Routing regret, under- and over-routing, and the quality/cost frontier.

Regret is the honest way to score a router: not "was the answer right?"
but "how much did choosing this route cost against the best route that
was available for this task?" Splitting it into quality regret and cost
regret matters, because the two failures are opposite and a single number
hides which one happened.

Under-routing and over-routing are defined against the measured matrix
rather than against intuition:

* **under-routed** — a cheaper-or-equal capability was chosen and a
  better-quality capability existed;
* **over-routed** — quality matched the best available, but a cheaper
  capability would have reached the same quality.

Both definitions need the matrix, which is why the matrix comes first.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class RouteScore:
    """One routed task, scored against the matrix."""

    query_id: str
    chosen: str
    oracle: str = ""
    chosen_quality: float = 0.0
    oracle_quality: float = 0.0
    chosen_cost: float = 0.0
    oracle_cost: float = 0.0
    chosen_utility: float = 0.0
    oracle_utility: float = 0.0
    quality_regret: float = 0.0
    cost_regret: float = 0.0
    utility_regret: float = 0.0
    under_routed: bool = False
    over_routed: bool = False
    cheapest_adequate: str = ""
    unmeasured: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RoutingReport:
    policy_type: str
    policy_version: str
    scores: list[RouteScore] = field(default_factory=list)
    route_counts: dict = field(default_factory=dict)
    totals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "policy_type": self.policy_type,
            "policy_version": self.policy_version,
            "route_counts": self.route_counts,
            "totals": self.totals,
            "scores": [score.to_dict() for score in self.scores],
        }


def score_routes(
    policy_type: str,
    policy_version: str,
    chosen_by_query: dict[str, str],
    matrix,
    utility,
    adequacy_threshold: float,
) -> RoutingReport:
    """Score a router's choices against the measured matrix."""
    report = RoutingReport(policy_type, policy_version)
    counts: dict[str, int] = {}
    for query_id, cells in matrix.by_query().items():
        measured = [cell for cell in cells if cell.measured]
        if not measured or query_id not in chosen_by_query:
            continue
        chosen_id = chosen_by_query[query_id]
        counts[chosen_id] = counts.get(chosen_id, 0) + 1
        by_capability = {cell.capability_id: cell for cell in measured}
        chosen_cell = by_capability.get(chosen_id)
        best_cell = max(
            measured,
            key=lambda cell: (utility.score(cell), cell.capability_id),
        )
        best_quality = max(utility.quality(cell) for cell in measured)
        adequate = [
            cell for cell in measured
            if utility.quality(cell) >= adequacy_threshold
        ]
        cheapest_adequate_cell = min(
            adequate or measured,
            key=lambda cell: (cell.cost_units, cell.capability_id),
        )
        if chosen_cell is None:
            report.scores.append(
                RouteScore(
                    query_id=query_id, chosen=chosen_id,
                    oracle=best_cell.capability_id, unmeasured=True,
                    cheapest_adequate=cheapest_adequate_cell.capability_id,
                )
            )
            continue
        chosen_quality = utility.quality(chosen_cell)
        score = RouteScore(
            query_id=query_id,
            chosen=chosen_id,
            oracle=best_cell.capability_id,
            chosen_quality=round(chosen_quality, 4),
            oracle_quality=round(utility.quality(best_cell), 4),
            chosen_cost=chosen_cell.cost_units,
            oracle_cost=best_cell.cost_units,
            chosen_utility=round(utility.score(chosen_cell), 4),
            oracle_utility=round(utility.score(best_cell), 4),
            quality_regret=round(best_quality - chosen_quality, 4),
            cost_regret=round(
                chosen_cell.cost_units - cheapest_adequate_cell.cost_units, 4
            ),
            utility_regret=round(
                utility.score(best_cell) - utility.score(chosen_cell), 4
            ),
            cheapest_adequate=cheapest_adequate_cell.capability_id,
        )
        score.under_routed = score.quality_regret > 1e-9
        score.over_routed = (
            not score.under_routed and score.cost_regret > 1e-9
        )
        report.scores.append(score)

    scored = [s for s in report.scores if not s.unmeasured]
    n = len(scored) or 1
    report.route_counts = dict(sorted(counts.items()))
    report.totals = {
        "tasks": len(scored),
        "mean_quality": round(sum(s.chosen_quality for s in scored) / n, 4),
        "mean_oracle_quality": round(
            sum(s.oracle_quality for s in scored) / n, 4
        ),
        "mean_cost_units": round(sum(s.chosen_cost for s in scored) / n, 4),
        "mean_oracle_cost": round(sum(s.oracle_cost for s in scored) / n, 4),
        "mean_utility": round(sum(s.chosen_utility for s in scored) / n, 4),
        "mean_quality_regret": round(
            sum(s.quality_regret for s in scored) / n, 4
        ),
        "mean_cost_regret": round(sum(s.cost_regret for s in scored) / n, 4),
        "mean_utility_regret": round(
            sum(s.utility_regret for s in scored) / n, 4
        ),
        "under_routed": sum(1 for s in scored if s.under_routed),
        "over_routed": sum(1 for s in scored if s.over_routed),
        "exact_oracle_match": sum(
            1 for s in scored if s.chosen == s.oracle
        ),
        "unmeasured_routes": sum(1 for s in report.scores if s.unmeasured),
    }
    return report


def pareto_frontier(points: dict[str, tuple[float, float]]) -> list[str]:
    """Names on the quality/cost frontier (higher quality, lower cost).

    A point is on the frontier when nothing else is at least as good on
    quality and strictly cheaper, or cheaper-or-equal and strictly better.
    """
    frontier: list[str] = []
    for name, (quality, cost) in points.items():
        dominated = any(
            other != name
            and other_quality >= quality
            and other_cost <= cost
            and (other_quality > quality or other_cost < cost)
            for other, (other_quality, other_cost) in points.items()
        )
        if not dominated:
            frontier.append(name)
    return sorted(frontier)


def headroom(matrix, utility) -> dict:
    """How much value perfect routing could add over the best fixed policy.

    This is the number that decides whether a Nexus has a subject. If the
    oracle barely beats the best single capability, routing is premature
    and the chapter says so.
    """
    fixed = matrix.fixed_policy_scores(utility)
    if not fixed:
        return {"available": False}
    best_fixed_utility = max(
        fixed.items(), key=lambda item: item[1]["utility"]
    )
    best_fixed_quality = max(
        fixed.items(), key=lambda item: item[1]["quality"]
    )
    oracle_quality = 0.0
    oracle_utility = 0.0
    oracle_cost = 0.0
    tasks = 0
    for _query_id, cells in matrix.by_query().items():
        measured = [cell for cell in cells if cell.measured]
        if not measured:
            continue
        tasks += 1
        best = max(
            measured, key=lambda cell: (utility.score(cell), cell.capability_id)
        )
        oracle_quality += max(utility.quality(cell) for cell in measured)
        oracle_utility += utility.score(best)
        oracle_cost += best.cost_units
    n = tasks or 1
    return {
        "available": True,
        "tasks": tasks,
        "best_fixed_by_utility": best_fixed_utility[0],
        "best_fixed_utility": best_fixed_utility[1]["utility"],
        "best_fixed_by_quality": best_fixed_quality[0],
        "best_fixed_quality": best_fixed_quality[1]["quality"],
        "best_fixed_cost": best_fixed_utility[1]["cost_units"],
        "oracle_quality": round(oracle_quality / n, 4),
        "oracle_utility": round(oracle_utility / n, 4),
        "oracle_cost": round(oracle_cost / n, 4),
        "quality_headroom": round(
            oracle_quality / n - best_fixed_quality[1]["quality"], 4
        ),
        "utility_headroom": round(
            oracle_utility / n - best_fixed_utility[1]["utility"], 4
        ),
    }
