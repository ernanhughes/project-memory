"""The capability registry: what the Nexus is allowed to choose between.

A capability is a memory mechanism the system can invoke, described well
enough for a router to reason about it without knowing how it works. The
registry exists so that adding a mechanism is a registration, not a
rewrite of the router — and so that later chapters can add temporal
resolution, belief resolution, or consolidated memory without touching
this module.

Two things are kept apart with some care:

* **identity** — the ``capability_id`` a policy names;
* **descriptor** — cost, strengths, and limitations in text a policy may
  read. Router-R1 conditions on exactly this kind of descriptor to
  generalise to models it never saw in training, and the same trick is
  what would let a new memory mechanism register itself here without
  retraining a router.

Nothing in a descriptor is ground truth about which capability wins. The
descriptors are *claims about intent*; the task-by-capability matrix is
what measures whether the claims hold.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable, Protocol

# Cost tiers, ordered. Used for "cheapest adequate" policies and for the
# escalation ladder; the actual measured costs come from the runs.
FREE = "free"
CHEAP = "cheap"
MODERATE = "moderate"
EXPENSIVE = "expensive"
COST_ORDER = (FREE, CHEAP, MODERATE, EXPENSIVE)


@dataclass(frozen=True)
class CapabilityDescriptor:
    """What a router may know about a capability without running it."""

    cost_tier: str
    strengths: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    provides_provenance: bool = False
    reads_derived_state: bool = False
    typical_latency_ms: float = 0.0
    typical_model_calls: int = 0

    def __post_init__(self) -> None:
        if self.cost_tier not in COST_ORDER:
            raise ValueError(f"unknown cost tier: {self.cost_tier}")

    def to_dict(self) -> dict:
        return asdict(self)


class CapabilityExecutor(Protocol):
    """Run one memory action and report capability-agnostic diagnostics."""

    def __call__(self, state, action):
        ...


@dataclass
class MemoryCapability:
    """One registered memory mechanism."""

    capability_id: str
    chapter: str
    summary: str
    descriptor: CapabilityDescriptor
    execute: Callable = field(repr=False, default=None)
    available: bool = True
    degraded: bool = False
    degraded_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "chapter": self.chapter,
            "summary": self.summary,
            "descriptor": self.descriptor.to_dict(),
            "available": self.available,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
        }

    def describe(self) -> str:
        """Text a language-model router can read."""
        lines = [
            f"{self.capability_id} (cost: {self.descriptor.cost_tier})",
            f"  {self.summary}",
        ]
        if self.descriptor.strengths:
            lines.append(f"  strengths: {'; '.join(self.descriptor.strengths)}")
        if self.descriptor.limitations:
            lines.append(
                f"  limitations: {'; '.join(self.descriptor.limitations)}"
            )
        if self.degraded:
            lines.append(f"  DEGRADED: {self.degraded_reason}")
        return "\n".join(lines)


class CapabilityRegistry:
    """The set of memory mechanisms available to the Nexus right now."""

    def __init__(self, version: str = "nexus-caps-v0.1") -> None:
        self.version = version
        self._capabilities: dict[str, MemoryCapability] = {}

    def register(self, capability: MemoryCapability) -> None:
        if capability.capability_id in self._capabilities:
            raise ValueError(
                f"capability already registered: {capability.capability_id}"
            )
        self._capabilities[capability.capability_id] = capability

    def get(self, capability_id: str) -> MemoryCapability:
        if capability_id not in self._capabilities:
            raise KeyError(f"unknown capability: {capability_id}")
        return self._capabilities[capability_id]

    def __contains__(self, capability_id: str) -> bool:
        return capability_id in self._capabilities

    def ids(self) -> list[str]:
        return sorted(self._capabilities)

    def available_ids(self) -> list[str]:
        """Registered, available, and not health-disabled.

        Health matters to routing: a stale graph index or an incomplete
        embedding index makes a capability a bad choice regardless of how
        well suited the question is to it.
        """
        return sorted(
            cid
            for cid, cap in self._capabilities.items()
            if cap.available and not cap.degraded
        )

    def degraded_ids(self) -> list[str]:
        return sorted(
            cid
            for cid, cap in self._capabilities.items()
            if cap.available and cap.degraded
        )

    def all(self) -> list[MemoryCapability]:
        return [self._capabilities[cid] for cid in self.ids()]

    def mark_degraded(self, capability_id: str, reason: str) -> None:
        capability = self.get(capability_id)
        capability.degraded = True
        capability.degraded_reason = reason

    def mark_unavailable(self, capability_id: str, reason: str = "") -> None:
        capability = self.get(capability_id)
        capability.available = False
        capability.degraded_reason = reason or capability.degraded_reason

    def cheapest(self, candidates: list[str] | None = None) -> str | None:
        """The lowest-cost-tier capability among the candidates."""
        pool = candidates if candidates is not None else self.available_ids()
        pool = [cid for cid in pool if cid in self._capabilities]
        if not pool:
            return None
        return min(
            pool,
            key=lambda cid: (
                COST_ORDER.index(self.get(cid).descriptor.cost_tier),
                cid,
            ),
        )

    def describe_all(self) -> str:
        return "\n".join(
            capability.describe() for capability in self.all()
        )

    def manifest(self) -> dict:
        return {
            "registry_version": self.version,
            "capabilities": [cap.to_dict() for cap in self.all()],
        }


# -- the capability identifiers this chapter registers ---------------------

NONE = "NONE"
RAG = "RAG"
GRAPH_BASIC = "GRAPH_BASIC"
GRAPH_LOCAL = "GRAPH_LOCAL"
GRAPH_GLOBAL = "GRAPH_GLOBAL"
GRAPH_DRIFT = "GRAPH_DRIFT"
ASSOCIATIVE = "ASSOCIATIVE"
RAW_EVIDENCE = "RAW_EVIDENCE"

# Descriptors are intent, not measurement. Each strength below is a
# hypothesis the task-by-capability matrix tests.
DESCRIPTORS: dict[str, tuple[str, str, CapabilityDescriptor]] = {
    NONE: (
        "1",
        "Answer from the reader alone, with no retrieved history.",
        CapabilityDescriptor(
            cost_tier=FREE,
            strengths=("questions the past does not bear on",),
            limitations=("no access to project history at all",),
            typical_model_calls=1,
        ),
    ),
    RAG: (
        "3",
        "Hybrid lexical and dense retrieval over raw history with "
        "reranking, then a bounded context.",
        CapabilityDescriptor(
            cost_tier=CHEAP,
            strengths=(
                "locating where something was discussed",
                "questions answered by one or two passages",
            ),
            limitations=(
                "no relationship structure",
                "no corpus-wide synthesis",
            ),
            provides_provenance=True,
            typical_model_calls=1,
        ),
    ),
    GRAPH_BASIC: (
        "4",
        "Vector search over the graph index's text units: the derived "
        "layer's own retrieval analogue.",
        CapabilityDescriptor(
            cost_tier=CHEAP,
            strengths=("passage-level lookup inside the derived index",),
            limitations=("largely duplicates plain retrieval",),
            provides_provenance=True,
            reads_derived_state=True,
            typical_model_calls=1,
        ),
    ),
    GRAPH_LOCAL: (
        "4",
        "Entity-centred search over graph neighbourhoods plus their "
        "source text.",
        CapabilityDescriptor(
            cost_tier=MODERATE,
            strengths=(
                "questions about a named entity and what it relates to",
                "relationships between artifacts",
            ),
            limitations=(
                "needs the question to link to graph entities",
                "weak on corpus-wide questions",
            ),
            provides_provenance=True,
            reads_derived_state=True,
            typical_model_calls=1,
        ),
    ),
    GRAPH_GLOBAL: (
        "4",
        "Map/reduce synthesis over community reports covering the whole "
        "corpus.",
        CapabilityDescriptor(
            cost_tier=EXPENSIVE,
            strengths=(
                "corpus-wide themes and summaries",
                "questions no single passage answers",
            ),
            limitations=(
                "expensive",
                "coarse for specific factual lookups",
            ),
            provides_provenance=True,
            reads_derived_state=True,
            typical_model_calls=6,
        ),
    ),
    GRAPH_DRIFT: (
        "4",
        "Community-report primer followed by iterative local follow-ups.",
        CapabilityDescriptor(
            cost_tier=EXPENSIVE,
            strengths=("questions needing both breadth and detail",),
            limitations=("the most expensive graph mode",),
            provides_provenance=True,
            reads_derived_state=True,
            typical_model_calls=8,
        ),
    ),
    ASSOCIATIVE: (
        "5",
        "Cue-conditioned activation spreading through the memory graph "
        "from seeded nodes.",
        CapabilityDescriptor(
            cost_tier=CHEAP,
            strengths=(
                "evidence reachable by a chain but not by resemblance",
                "indirect multi-hop questions",
            ),
            limitations=(
                "no gain when direct retrieval already succeeds",
                "propagates extraction errors along false edges",
                "depends on seed quality",
            ),
            provides_provenance=True,
            reads_derived_state=True,
            typical_model_calls=1,
        ),
    ),
    RAW_EVIDENCE: (
        "3",
        "A wide, low-selectivity sweep of raw source artifacts: the "
        "fallback when derived memory is not trusted.",
        CapabilityDescriptor(
            cost_tier=MODERATE,
            strengths=(
                "bypasses all derived interpretation",
                "the floor under every other capability",
            ),
            limitations=("low precision", "large context cost"),
            provides_provenance=True,
            typical_model_calls=1,
        ),
    ),
}


def build_registry(
    executors: dict[str, Callable],
    version: str = "nexus-caps-v0.1",
) -> CapabilityRegistry:
    """Register every capability for which an executor was supplied.

    Capabilities without an executor are simply absent: the registry
    never advertises something the system cannot actually run.
    """
    registry = CapabilityRegistry(version=version)
    for capability_id, (chapter, summary, descriptor) in DESCRIPTORS.items():
        executor = executors.get(capability_id)
        if executor is None:
            continue
        registry.register(
            MemoryCapability(
                capability_id=capability_id,
                chapter=chapter,
                summary=summary,
                descriptor=descriptor,
                execute=executor,
            )
        )
    return registry
