"""Nexus health: is the control layer itself sound?

Two kinds of check, kept apart because they fail for different reasons.

*Registry health* asks whether the capabilities the router may choose
between actually exist and work. A router choosing a capability whose
index is stale is making a correct-looking decision with a wrong
outcome, and that is a routing failure the router could have avoided if
it had been told.

*Policy health* asks whether the router itself is well-formed: does it
leak evaluator fields, does it have a recorded version, does it collapse
onto one capability. Route collapse is the mixture-of-experts failure
mode reappearing here — a gate that always picks one expert has stopped
being a gate — and it is worth detecting even when accuracy looks fine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..state.features import audit_state


@dataclass
class HealthIssue:
    check: str
    detail: str


@dataclass
class NexusHealthReport:
    healthy: bool = True
    registered: int = 0
    available: int = 0
    degraded: int = 0
    capability_ids: list[str] = field(default_factory=list)
    route_distribution: dict = field(default_factory=dict)
    unused_capabilities: list[str] = field(default_factory=list)
    collapsed_onto: str | None = None
    policy_versions: list[str] = field(default_factory=list)
    leakage_fields: list[str] = field(default_factory=list)
    issues: list[HealthIssue] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "Memory Nexus Health",
            "",
            f"Capabilities registered:  {self.registered}",
            f"Available:                {self.available}",
            f"Degraded:                 {self.degraded}",
            f"Registered ids:           {', '.join(self.capability_ids)}",
        ]
        if self.route_distribution:
            lines.append("")
            lines.append("Route distribution:")
            for capability_id, count in sorted(
                self.route_distribution.items()
            ):
                lines.append(f"  {capability_id:<16} {count}")
            if self.unused_capabilities:
                lines.append(
                    f"  never chosen: {', '.join(self.unused_capabilities)}"
                )
        if self.policy_versions:
            lines.append("")
            lines.append(
                f"Policy versions seen:     {', '.join(self.policy_versions)}"
            )
        lines.append("")
        if self.issues:
            lines.append("Issues:")
            for issue in self.issues:
                lines.append(f"  [{issue.check}] {issue.detail}")
        else:
            lines.append("No control-layer issues detected.")
        lines.append(f"Verdict: {'HEALTHY' if self.healthy else 'UNHEALTHY'}")
        lines.append(
            "Control-layer health is not memory quality and not routing "
            "quality; the matrix and the scorecard measure those."
        )
        return "\n".join(lines) + "\n"


def check_nexus(
    registry, episodes=None, states=None
) -> NexusHealthReport:
    """Structural checks over the registry and, if supplied, routed runs."""
    report = NexusHealthReport(
        registered=len(registry.ids()),
        available=len(registry.available_ids()),
        degraded=len(registry.degraded_ids()),
        capability_ids=registry.ids(),
    )

    def flag(check: str, detail: str) -> None:
        report.issues.append(HealthIssue(check, detail))
        report.healthy = False

    if not registry.ids():
        flag("empty-registry", "no capabilities registered")
    for capability in registry.all():
        if capability.execute is None:
            flag(
                "no-executor",
                f"{capability.capability_id} is registered without an "
                "executor and can never run",
            )
        if capability.degraded:
            report.issues.append(
                HealthIssue(
                    "degraded-capability",
                    f"{capability.capability_id}: "
                    f"{capability.degraded_reason}",
                )
            )

    for state in states or []:
        found = audit_state(state)
        for name in found:
            if name not in report.leakage_fields:
                report.leakage_fields.append(name)
    if report.leakage_fields:
        flag(
            "feature-leakage",
            "router state carries evaluator-only fields: "
            + ", ".join(report.leakage_fields),
        )

    if episodes:
        counts: dict[str, int] = {}
        versions: list[str] = []
        for episode in episodes:
            for capability_id in episode.actions:
                counts[capability_id] = counts.get(capability_id, 0) + 1
            if episode.policy_version not in versions:
                versions.append(episode.policy_version)
        report.route_distribution = dict(sorted(counts.items()))
        report.policy_versions = versions
        report.unused_capabilities = [
            capability_id
            for capability_id in registry.available_ids()
            if capability_id not in counts
        ]
        total = sum(counts.values())
        if total and len(counts) == 1:
            report.collapsed_onto = next(iter(counts))
            report.issues.append(
                HealthIssue(
                    "route-collapse",
                    f"every route went to {report.collapsed_onto}; the "
                    "router is a fixed policy in disguise",
                )
            )
        loops = sum(
            1 for episode in episodes
            if "ROUTER_LOOP" in episode.router_failures
        )
        if loops:
            flag("loop-guard-fired", f"{loops} episodes hit the repeat guard")
        overruns = sum(
            1 for episode in episodes
            if "ROUTER_COST_OVERRUN" in episode.router_failures
        )
        if overruns:
            report.issues.append(
                HealthIssue(
                    "cost-guard-fired",
                    f"{overruns} episodes hit the cost ceiling",
                )
            )
    return report
