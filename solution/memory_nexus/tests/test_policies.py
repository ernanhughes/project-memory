"""Every policy: fixed, random, rules, classifier, oracle, sequential."""

import json

import pytest

from memory_nexus.capabilities.registry import (
    ASSOCIATIVE,
    GRAPH_GLOBAL,
    GRAPH_LOCAL,
    NONE,
    RAG,
    RAW_EVIDENCE,
)
from memory_nexus.config import ClassifierConfig, NexusConfig
from memory_nexus.demo import build_stub_registry
from memory_nexus.policies.classifier import (
    ClassifierPolicy,
    LogisticRouter,
    load_router,
    save_router,
)
from memory_nexus.policies.fixed import FixedPolicy, RandomPolicy
from memory_nexus.policies.llm import LLMPolicy, _extract_json
from memory_nexus.policies.oracle import CheapestAdequateOracle, OraclePolicy
from memory_nexus.policies.rules import LeakyFamilyPolicy, RulePolicy
from memory_nexus.policies.sequential import SequentialPolicy
from memory_nexus.state.features import feature_vector, build_state
from memory_nexus.state.model import ActionObservation, MEDIUM


@pytest.fixture
def registry():
    return build_stub_registry()


def state_for(text, registry, query_id="q"):
    return build_state(query_id, text, tuple(registry.available_ids()))


# -- fixed and random -------------------------------------------------------


def test_fixed_policy_is_deterministic(registry) -> None:
    policy = FixedPolicy(RAG)
    for text in ("anything", "something else", "a third question"):
        action = policy.decide(state_for(text, registry), registry)
        assert action.capability == RAG
    assert len(policy.traces) == 3


def test_random_policy_is_reproducible_per_query(registry) -> None:
    first = RandomPolicy(seed=3)
    second = RandomPolicy(seed=3)
    state = state_for("what happened", registry, "q7")
    assert (
        first.decide(state, registry).capability
        == second.decide(state, registry).capability
    )


def test_random_policy_varies_across_queries(registry) -> None:
    policy = RandomPolicy(seed=1)
    choices = {
        policy.decide(state_for("q", registry, f"q{i}"), registry).capability
        for i in range(12)
    }
    assert len(choices) > 1


def test_random_policy_abstains_with_no_capabilities(registry) -> None:
    state = build_state("q", "text", ())
    # An explicitly empty available list must be respected.
    action = RandomPolicy(seed=1).decide(state, EmptyRegistry())
    assert action.capability == "ABSTAIN"


class EmptyRegistry:
    version = "empty"

    def available_ids(self):
        return []

    def degraded_ids(self):
        return []

    def ids(self):
        return []

    def cheapest(self, candidates=None):
        return None

    def __contains__(self, item):
        return False


# -- rules -------------------------------------------------------------------


def test_rules_route_synthesis_wording_to_global(registry) -> None:
    action = RulePolicy().decide(
        state_for("What major themes run across the whole history?", registry),
        registry,
    )
    assert action.capability == GRAPH_GLOBAL
    assert action.retrieval_budget == "HIGH"


def test_rules_route_relational_wording_to_graph_local(registry) -> None:
    action = RulePolicy().decide(
        state_for("How is the stall connected to the decision?", registry),
        registry,
    )
    assert action.capability == GRAPH_LOCAL


def test_rules_default_to_the_cheap_capability(registry) -> None:
    action = RulePolicy().decide(
        state_for("What event store should new services use?", registry),
        registry,
    )
    assert action.capability == RAG


def test_rules_fall_back_when_the_preferred_capability_is_missing() -> None:
    registry = build_stub_registry()
    registry.mark_unavailable(GRAPH_GLOBAL, "not built")
    policy = RulePolicy()
    action = policy.decide(
        state_for("What major themes run across the whole history?", registry),
        registry,
    )
    assert action.capability == RAG
    assert policy.traces[-1].fallback_used


def test_rules_record_their_reasons(registry) -> None:
    policy = RulePolicy()
    policy.decide(state_for("Why was it chosen?", registry), registry)
    trace = policy.traces[-1]
    assert trace.reason_features
    assert trace.scores  # signal values are recorded, not just the choice


def test_leaky_family_policy_is_labelled_as_a_control(registry) -> None:
    policy = LeakyFamilyPolicy({"q": "global"})
    action = policy.decide(state_for("anything at all", registry), registry)
    assert action.capability == GRAPH_GLOBAL
    assert "LEAKED-LABEL" in policy.traces[-1].reason_features
    assert "evaluator metadata" in policy.traces[-1].notes


# -- oracle -------------------------------------------------------------------


def test_oracle_follows_the_measured_choice(registry) -> None:
    policy = OraclePolicy({"q": ASSOCIATIVE})
    assert policy.decide(state_for("x", registry), registry).capability == (
        ASSOCIATIVE
    )


def test_oracle_falls_back_when_its_choice_is_unavailable() -> None:
    registry = build_stub_registry()
    registry.mark_unavailable(ASSOCIATIVE, "gone")
    policy = OraclePolicy({"q": ASSOCIATIVE})
    action = policy.decide(state_for("x", registry), registry)
    assert action.capability != ASSOCIATIVE
    assert policy.traces[-1].fallback_used


def test_cheapest_adequate_oracle_records_its_intent(registry) -> None:
    policy = CheapestAdequateOracle({"q": RAG})
    action = policy.decide(state_for("x", registry), registry)
    assert action.capability == RAG
    assert "cheapest" in action.reason


# -- classifier ----------------------------------------------------------------


def training_samples(registry):
    texts = {
        "What major themes run across the whole project history?": GRAPH_GLOBAL,
        "What overall patterns appear throughout the history?": GRAPH_GLOBAL,
        "How is the stall connected to the decision?": GRAPH_LOCAL,
        "Which incidents influenced the decision?": GRAPH_LOCAL,
        "What event store should new services use?": RAG,
        "What did the team decide about Redis?": RAG,
    }
    return [
        (feature_vector(state_for(text, registry)), label)
        for text, label in texts.items()
    ]


def test_classifier_trains_and_reduces_loss(registry) -> None:
    labels = sorted({label for _f, label in training_samples(registry)})
    router = LogisticRouter(labels, ClassifierConfig())
    report = router.fit(training_samples(registry))
    assert report["trained"]
    assert report["final_loss"] < report["initial_loss"]


def test_classifier_emits_a_probability_distribution(registry) -> None:
    labels = sorted({label for _f, label in training_samples(registry)})
    router = LogisticRouter(labels, ClassifierConfig())
    router.fit(training_samples(registry))
    probabilities = router.predict(
        feature_vector(state_for("What overall themes?", registry))
    )
    assert len(probabilities) == len(labels)
    assert abs(sum(probabilities) - 1.0) < 1e-9
    assert all(0.0 <= p <= 1.0 for p in probabilities)


def test_classifier_with_no_samples_reports_untrained(registry) -> None:
    router = LogisticRouter([RAG], ClassifierConfig())
    assert router.fit([])["trained"] is False


def test_classifier_policy_only_chooses_available_capabilities() -> None:
    registry = build_stub_registry()
    samples = training_samples(registry)
    labels = sorted({label for _f, label in samples})
    router = LogisticRouter(labels, ClassifierConfig())
    router.fit(samples)
    registry.mark_unavailable(GRAPH_GLOBAL, "not built")
    policy = ClassifierPolicy(router, ClassifierConfig())
    action = policy.decide(
        state_for("What major themes run across the history?", registry),
        registry,
    )
    assert action.capability != GRAPH_GLOBAL
    assert action.capability in registry.available_ids()


def test_classifier_threshold_falls_back(registry) -> None:
    samples = training_samples(registry)
    labels = sorted({label for _f, label in samples})
    router = LogisticRouter(labels, ClassifierConfig())
    router.fit(samples)
    config = ClassifierConfig(abstain_below=1.1)  # never confident enough
    policy = ClassifierPolicy(router, config)
    action = policy.decide(state_for("anything", registry), registry)
    assert action.capability == RAG
    assert policy.low_confidence_fallbacks == 1
    assert policy.traces[-1].fallback_used


def test_classifier_round_trips_through_disk(registry, tmp_path) -> None:
    samples = training_samples(registry)
    labels = sorted({label for _f, label in samples})
    router = LogisticRouter(labels, ClassifierConfig())
    router.fit(samples)
    path = save_router(router, tmp_path / "router.json")
    restored = load_router(path, ClassifierConfig())
    features = feature_vector(state_for("What themes?", registry))
    assert restored.predict(features) == router.predict(features)


def test_classifier_is_deterministic(registry) -> None:
    samples = training_samples(registry)
    labels = sorted({label for _f, label in samples})
    first = LogisticRouter(labels, ClassifierConfig())
    first.fit(samples)
    second = LogisticRouter(labels, ClassifierConfig())
    second.fit(samples)
    assert first.weights == second.weights


# -- generative router ----------------------------------------------------------


def test_router_json_extraction_handles_surrounding_prose() -> None:
    parsed = _extract_json(
        'Sure! Here is my choice:\n{"capability": "RAG", "budget": "LOW"}\nOK?'
    )
    assert parsed == {"capability": "RAG", "budget": "LOW"}
    assert _extract_json("no json here") is None
    assert _extract_json("{not valid json}") is None


def test_llm_policy_falls_back_on_a_malformed_response(registry) -> None:
    policy = LLMPolicy(NexusConfig().router_model)
    policy._ask = lambda prompt: "I think you should use the graph, maybe."
    action = policy.decide(state_for("anything", registry), registry)
    assert action.capability == RAG
    assert policy.schema_failures == 1
    assert policy.traces[-1].fallback_used


def test_llm_policy_rejects_an_unavailable_capability(registry) -> None:
    policy = LLMPolicy(NexusConfig().router_model)
    policy._ask = lambda prompt: '{"capability": "TELEPATHY"}'
    action = policy.decide(state_for("anything", registry), registry)
    assert action.capability == RAG
    assert policy.schema_failures == 1


def test_llm_policy_accepts_a_valid_bounded_choice(registry) -> None:
    policy = LLMPolicy(NexusConfig().router_model)
    policy._ask = lambda prompt: json.dumps(
        {"capability": GRAPH_LOCAL, "budget": "LOW", "reason": "entities"}
    )
    action = policy.decide(state_for("anything", registry), registry)
    assert action.capability == GRAPH_LOCAL
    assert action.retrieval_budget == "LOW"
    assert policy.schema_failures == 0


def test_llm_policy_coerces_an_unknown_budget(registry) -> None:
    policy = LLMPolicy(NexusConfig().router_model)
    policy._ask = lambda prompt: json.dumps(
        {"capability": RAG, "budget": "GIGANTIC"}
    )
    assert policy.decide(
        state_for("x", registry), registry
    ).retrieval_budget == MEDIUM


def test_llm_policy_survives_a_transport_failure(registry) -> None:
    policy = LLMPolicy(NexusConfig().router_model)

    def boom(prompt):
        raise OSError("connection refused")

    policy._ask = boom
    action = policy.decide(state_for("x", registry), registry)
    assert action.capability == RAG
    assert policy.traces[-1].fallback_used


def test_llm_policy_manifest_freezes_the_prompt(registry) -> None:
    policy = LLMPolicy(NexusConfig().router_model)
    manifest = policy.manifest()
    for key in ("model", "temperature", "seed", "prompt_version",
                "prompt_sha1"):
        assert key in manifest


def test_route_variance_measures_agreement(registry) -> None:
    from memory_nexus.policies.llm import measure_variance

    policy = LLMPolicy(NexusConfig().router_model)
    responses = iter(
        ['{"capability": "RAG"}', '{"capability": "RAG"}',
         '{"capability": "ASSOCIATIVE"}']
    )
    policy._ask = lambda prompt: next(responses)
    report = measure_variance(
        policy, state_for("x", registry), registry, repeats=3
    )
    assert report["modal_choice"] == RAG
    assert report["agreement"] == pytest.approx(2 / 3)


# -- sequential ------------------------------------------------------------------


def test_sequential_starts_with_the_cheap_capability(registry) -> None:
    action = SequentialPolicy().next_action(
        state_for("anything", registry), [], registry
    )
    assert action.capability == RAG


def test_sequential_stops_when_evidence_is_sufficient(registry) -> None:
    observation = ActionObservation(
        capability_id=RAG, evidence_count=3, top_score=0.9,
        provenance_available=True,
    )
    action = SequentialPolicy().next_action(
        state_for("anything", registry), [observation], registry
    )
    assert action.capability == "STOP"


def test_sequential_escalates_when_nothing_came_back(registry) -> None:
    empty = ActionObservation(capability_id=RAG, evidence_count=0)
    action = SequentialPolicy().next_action(
        state_for("What major themes run across the history?", registry),
        [empty], registry,
    )
    assert action.capability == GRAPH_GLOBAL


def test_sequential_escalates_to_associative_for_indirect_wording(
    registry,
) -> None:
    empty = ActionObservation(capability_id=RAG, evidence_count=0)
    action = SequentialPolicy().next_action(
        state_for("What untidy work was left over?", registry),
        [empty], registry,
    )
    assert action.capability == ASSOCIATIVE


def test_sequential_abstains_when_everything_has_been_tried(registry) -> None:
    observations = [
        ActionObservation(capability_id=cid, evidence_count=0)
        for cid in (RAG, GRAPH_GLOBAL, GRAPH_LOCAL, ASSOCIATIVE, RAW_EVIDENCE)
    ]
    action = SequentialPolicy(max_actions=9).next_action(
        state_for("nothing matches this", registry), observations, registry
    )
    assert action.capability == "ABSTAIN"


def test_sequential_stops_when_the_budget_is_exhausted(registry) -> None:
    observations = [
        ActionObservation(capability_id=RAG, evidence_count=0),
        ActionObservation(capability_id=GRAPH_LOCAL, evidence_count=0),
        ActionObservation(capability_id=ASSOCIATIVE, evidence_count=0),
    ]
    action = SequentialPolicy(max_actions=3).next_action(
        state_for("x", registry), observations, registry
    )
    assert action.capability == "STOP"
    assert "budget-exhausted" in action.reason


def test_sequential_requires_provenance_before_stopping(registry) -> None:
    unprovenanced = ActionObservation(
        capability_id=RAG, evidence_count=2, provenance_available=False
    )
    action = SequentialPolicy().next_action(
        state_for("x", registry), [unprovenanced], registry
    )
    assert action.capability != "STOP"
