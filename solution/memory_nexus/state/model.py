"""The types the Memory Nexus decides over.

Three objects carry the whole control problem:

``MemoryState``
    Everything the router may look at. The list is closed on purpose: a
    router that can see the ledger's task family, the expected sources,
    or the answer has not solved routing, it has been told the answer.
    Section "Observable state" in the chapter explains each field and why
    it is admissible.

``MemoryAction``
    What the router decides. Not a label — a capability *plus* the
    budgets and requirements under which it runs, because "use the graph"
    and "use the graph with three hops and provenance required" are
    different decisions with different costs.

``ActionObservation``
    What came back. This is what makes sequential control possible: the
    router sees diagnostics from the action it just took before choosing
    the next one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Budget tiers. A small discrete ladder rather than a continuous space:
# three values per axis are enough to test whether effort routing helps,
# and the exact numbers behind each tier are frozen in ``config``.
LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
BUDGET_TIERS = (LOW, MEDIUM, HIGH)

# Terminal decisions the router may take instead of a memory capability.
STOP = "STOP"
ABSTAIN = "ABSTAIN"
ASK_HUMAN = "ASK_HUMAN"
TERMINAL_ACTIONS = (STOP, ABSTAIN, ASK_HUMAN)


@dataclass(frozen=True)
class MemoryState:
    """Everything the router is allowed to see.

    Every field here is derivable before the answer exists. Nothing in
    this object is read from the evaluator's ledger; the leakage test in
    ``tests/test_leakage.py`` asserts that by construction.
    """

    query_id: str
    query_text: str
    # -- cheap text features ------------------------------------------
    query_tokens: int = 0
    interrogative: str = ""  # what | where | why | when | which | how | none
    cue_terms: tuple[str, ...] = ()
    # Signals read off the query text, never off a ledger label. The
    # names deliberately say "signal": they are hypotheses about what the
    # question wants, and the experiments measure how good they are.
    locational_signal: float = 0.0
    relational_signal: float = 0.0
    synthesis_signal: float = 0.0
    temporal_signal: float = 0.0
    causal_signal: float = 0.0
    counterfactual_signal: float = 0.0
    # 1.0 only when the question explicitly disclaims project history.
    generality_signal: float = 0.0
    # -- system state ---------------------------------------------------
    linked_entities: tuple[str, ...] = ()
    available_capabilities: tuple[str, ...] = ()
    degraded_capabilities: tuple[str, ...] = ()
    context_budget: int = 8
    latency_budget_ms: float = 0.0
    # -- diagnostics from prior actions in this episode -------------------
    actions_taken: tuple[str, ...] = ()
    spent_cost_units: float = 0.0
    spent_latency_ms: float = 0.0
    last_evidence_count: int = 0
    last_top_score: float = 0.0
    last_score_margin: float = 0.0
    last_abstained: bool = False
    disagreement: bool = False
    disagreement_detail: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("cue_terms", "linked_entities", "available_capabilities",
                    "degraded_capabilities", "actions_taken"):
            data[key] = list(data[key])
        return data

    def with_observation(self, observation: "ActionObservation") -> "MemoryState":
        """Fold one action's result back into the state for the next step."""
        import dataclasses

        return dataclasses.replace(
            self,
            actions_taken=self.actions_taken + (observation.capability_id,),
            spent_cost_units=self.spent_cost_units + observation.cost_units,
            spent_latency_ms=self.spent_latency_ms + observation.latency_ms,
            last_evidence_count=observation.evidence_count,
            last_top_score=observation.top_score,
            last_score_margin=observation.score_margin,
            last_abstained=observation.abstained,
        )


@dataclass(frozen=True)
class MemoryAction:
    """A memory decision: which capability, under what budget.

    ``capability`` may be a registered capability id or one of the
    terminal actions. Terminal actions carry no budget.
    """

    capability: str
    retrieval_budget: str = MEDIUM
    context_budget: int = 8
    require_provenance: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        if self.retrieval_budget not in BUDGET_TIERS:
            raise ValueError(f"unknown budget tier: {self.retrieval_budget}")

    @property
    def is_terminal(self) -> bool:
        return self.capability in TERMINAL_ACTIONS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ActionObservation:
    """What one executed memory action produced.

    The fields are deliberately capability-agnostic. A router that
    branched on "the GraphRAG answer text contains X" would be coupled to
    one backend; these diagnostics are available from every capability.
    """

    capability_id: str
    evidence_count: int = 0
    source_ids: list[str] = field(default_factory=list)
    answer_text: str = ""
    abstained: bool = False
    top_score: float = 0.0
    score_margin: float = 0.0
    provenance_available: bool = False
    context_tokens: int = 0
    latency_ms: float = 0.0
    cost_units: float = 0.0
    model_calls: int = 0
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CostRecord:
    """Raw cost dimensions, never collapsed before they are reported."""

    latency_ms: float = 0.0
    context_tokens: int = 0
    model_calls: int = 0
    graph_expansions: int = 0
    cost_units: float = 0.0

    def add(self, other: "CostRecord") -> None:
        self.latency_ms += other.latency_ms
        self.context_tokens += other.context_tokens
        self.model_calls += other.model_calls
        self.graph_expansions += other.graph_expansions
        self.cost_units += other.cost_units

    def to_dict(self) -> dict:
        return asdict(self)
