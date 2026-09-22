"""Capability registry, observable state, and the leakage boundary."""

import pytest

from memory_nexus.capabilities.registry import (
    CHEAP,
    COST_ORDER,
    EXPENSIVE,
    FREE,
    ASSOCIATIVE,
    GRAPH_GLOBAL,
    GRAPH_LOCAL,
    NONE,
    RAG,
    CapabilityDescriptor,
    CapabilityRegistry,
    MemoryCapability,
    build_registry,
)
from memory_nexus.demo import build_stub_registry
from memory_nexus.state.features import (
    FEATURE_NAMES,
    FORBIDDEN_FIELDS,
    audit_state,
    build_state,
    feature_vector,
    interrogative_of,
    tokenise,
)
from memory_nexus.state.model import (
    BUDGET_TIERS,
    HIGH,
    LOW,
    MEDIUM,
    ActionObservation,
    MemoryAction,
)


def descriptor(tier=CHEAP):
    return CapabilityDescriptor(cost_tier=tier)


def capability(cid, tier=CHEAP, executor=lambda s, a: None):
    return MemoryCapability(
        capability_id=cid, chapter="x", summary="s",
        descriptor=descriptor(tier), execute=executor,
    )


# -- registry -------------------------------------------------------------


def test_registration_and_lookup() -> None:
    registry = CapabilityRegistry()
    registry.register(capability("A"))
    assert "A" in registry
    assert registry.get("A").capability_id == "A"
    assert registry.ids() == ["A"]


def test_duplicate_registration_is_rejected() -> None:
    registry = CapabilityRegistry()
    registry.register(capability("A"))
    with pytest.raises(ValueError):
        registry.register(capability("A"))


def test_unknown_capability_is_rejected() -> None:
    with pytest.raises(KeyError):
        CapabilityRegistry().get("nope")


def test_unknown_cost_tier_is_rejected() -> None:
    with pytest.raises(ValueError):
        CapabilityDescriptor(cost_tier="bargain")


def test_unavailable_capability_leaves_the_candidate_set() -> None:
    registry = CapabilityRegistry()
    registry.register(capability("A"))
    registry.register(capability("B"))
    registry.mark_unavailable("B", "backend missing")
    assert registry.available_ids() == ["A"]
    assert "B" in registry.ids()


def test_health_degraded_capability_leaves_the_candidate_set() -> None:
    """Routing must be able to see and avoid an unhealthy subsystem."""
    registry = CapabilityRegistry()
    registry.register(capability("A"))
    registry.register(capability("B"))
    registry.mark_degraded("B", "index stale")
    assert registry.available_ids() == ["A"]
    assert registry.degraded_ids() == ["B"]
    assert "index stale" in registry.get("B").describe()


def test_cheapest_respects_the_cost_order() -> None:
    registry = CapabilityRegistry()
    registry.register(capability("EXP", EXPENSIVE))
    registry.register(capability("FREEBIE", FREE))
    registry.register(capability("MID", CHEAP))
    assert registry.cheapest() == "FREEBIE"
    assert registry.cheapest(["EXP", "MID"]) == "MID"
    assert registry.cheapest([]) is None


def test_build_registry_skips_capabilities_without_executors() -> None:
    registry = build_registry({RAG: lambda s, a: None})
    assert registry.ids() == [RAG]
    assert GRAPH_LOCAL not in registry


def test_descriptors_are_readable_by_a_language_model_router() -> None:
    registry = build_stub_registry()
    text = registry.describe_all()
    for capability_id in (RAG, GRAPH_LOCAL, GRAPH_GLOBAL, ASSOCIATIVE, NONE):
        assert capability_id in text
    assert "cost:" in text
    assert "strengths:" in text


def test_registry_manifest_records_every_capability() -> None:
    manifest = build_stub_registry().manifest()
    assert manifest["registry_version"]
    assert len(manifest["capabilities"]) == 6
    assert all("descriptor" in c for c in manifest["capabilities"])


# -- state ----------------------------------------------------------------


def test_signals_are_derived_from_the_query_text_only() -> None:
    state = build_state(
        "q", "What major architectural themes run through the history?",
        ("RAG",),
    )
    assert state.synthesis_signal > 0
    assert state.interrogative == "what"
    assert state.query_tokens > 0


def test_relational_and_causal_signals_separate() -> None:
    relational = build_state(
        "q", "How is the stall connected to the decision?", ("RAG",)
    )
    causal = build_state("q", "Why was PostgreSQL chosen?", ("RAG",))
    assert relational.relational_signal > 0
    assert causal.causal_signal > 0
    assert causal.relational_signal == 0.0


def test_signals_are_length_normalised() -> None:
    """A long question must not score higher on every signal at once."""
    short = build_state("q", "What themes?", ("RAG",))
    padded = build_state(
        "q",
        "What themes emerged, considering the various unrelated details "
        "about scheduling and staffing and office arrangements?",
        ("RAG",),
    )
    assert padded.synthesis_signal < short.synthesis_signal


def test_tokenise_drops_stopwords_and_keeps_identifiers() -> None:
    tokens = tokenise("Where was adr-007 discussed in the session?")
    assert "adr-007" in tokens and "the" not in tokens


def test_interrogative_detection() -> None:
    assert interrogative_of("Why did we?") == "why"
    assert interrogative_of("Tell me about it.") == "none"


def test_feature_vector_width_matches_declared_names() -> None:
    state = build_state("q", "What runs in production now?", ("RAG",))
    assert len(feature_vector(state)) == len(FEATURE_NAMES)
    assert all(isinstance(value, float) for value in feature_vector(state))


def test_state_carries_no_evaluator_fields() -> None:
    """The homunculus guard: the router may not see the answer key."""
    state = build_state("q", "What event store?", ("RAG",))
    assert audit_state(state) == []
    for name in FORBIDDEN_FIELDS:
        assert not hasattr(state, name), name


def test_audit_detects_a_leaky_state_object() -> None:
    class Leaky:
        family = "decision"
        expected_sources = ("adr-007.md",)

    found = audit_state(Leaky())
    assert "family" in found and "expected_sources" in found


def test_observation_folds_into_the_next_state() -> None:
    state = build_state("q", "What event store?", ("RAG",))
    observation = ActionObservation(
        capability_id="RAG", evidence_count=3, top_score=0.8,
        score_margin=0.2, cost_units=1.0, latency_ms=120.0,
    )
    nxt = state.with_observation(observation)
    assert nxt.actions_taken == ("RAG",)
    assert nxt.last_evidence_count == 3
    assert nxt.spent_cost_units == 1.0
    # The original is unchanged: state is immutable per step.
    assert state.actions_taken == ()


# -- actions ----------------------------------------------------------------


def test_action_rejects_an_unknown_budget_tier() -> None:
    with pytest.raises(ValueError):
        MemoryAction(capability=RAG, retrieval_budget="ENORMOUS")


def test_budget_tiers_are_the_declared_ladder() -> None:
    assert BUDGET_TIERS == (LOW, MEDIUM, HIGH)
    assert COST_ORDER[0] == FREE and COST_ORDER[-1] == EXPENSIVE


def test_terminal_actions_are_recognised() -> None:
    assert MemoryAction(capability="STOP").is_terminal
    assert MemoryAction(capability="ABSTAIN").is_terminal
    assert MemoryAction(capability="ASK_HUMAN").is_terminal
    assert not MemoryAction(capability=RAG).is_terminal
