"""Turning a query and a system snapshot into observable router state.

The hard constraint here is the one the chapter calls the homunculus
problem: a router that already knows the answer has not routed, it has
answered. Everything in this module is computed from the query string
and from system availability — never from the evaluator's task family,
expected sources, or expected state.

The signals are lexical and deliberately crude. That is a design choice
with a purpose: if a crude signal routes as well as a language model
reading the question, the chapter has learned something about how much
interpretation routing actually needs.
"""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9_.\-]+")

STOPWORDS = frozenset(
    """
    a an and are as at be been by did do does for from had has have in
    into is it its of on or should that the their them then there these
    they this to was we were will with would you your
    """.split()
)

INTERROGATIVES = ("what", "where", "why", "when", "which", "who", "how")

# Signal vocabularies. Each is a hypothesis about what a question wants
# from memory, testable by whether routing on it beats routing without
# it. None of them is a ledger label.
LOCATIONAL = frozenset(
    "where discuss discussed mention mentioned record recorded find locate "
    "document documented said say wrote written session".split()
)
RELATIONAL = frozenset(
    "influence influenced connect connected connection between related "
    "relationship depend depends caused cause leads led link linked "
    "involving involved traced trace".split()
)
SYNTHESIS = frozenset(
    "overall summary summarise summarize themes theme main major overview "
    "across throughout general pattern patterns trends landscape "
    "everything history all".split()
)
TEMPORAL = frozenset(
    "now today current currently still latest recent then previously "
    "originally before after during when march june july august since "
    "supersede superseded outdated stale".split()
)
CAUSAL = frozenset(
    "why because reason rationale motivated justification evidence "
    "behind led caused prompted grounds basis".split()
)
COUNTERFACTUAL = frozenset(
    "instead should would could alternative rather next new another "
    "planning propose proposal recommend".split()
)
# Explicit markers that a question is asking for general knowledge rather
# than for this project's history. Narrow on purpose: detecting that
# memory is *not* needed from wording alone is largely unsolved, and a
# broad heuristic here would route real questions to no memory at all.
GENERALITY_MARKERS = (
    "without reference to this project",
    "in general terms",
    "in general,",
    "generally speaking",
    "regardless of this project",
    "independent of this project",
)


def tokenise(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN.findall(text.lower())
        if token not in STOPWORDS and len(token) > 1
    ]


def _signal(tokens: set[str], vocabulary: frozenset[str]) -> float:
    """Share of the query's content words drawn from one vocabulary.

    Normalised by query length so that a long question does not score
    higher on every signal simply by containing more words.
    """
    if not tokens:
        return 0.0
    return len(tokens & vocabulary) / len(tokens)


def generality_signal(text: str) -> float:
    """1.0 when the question explicitly disclaims the project's history."""
    lowered = text.lower()
    return 1.0 if any(m in lowered for m in GENERALITY_MARKERS) else 0.0


def interrogative_of(text: str) -> str:
    lowered = text.lower()
    for word in INTERROGATIVES:
        if re.search(rf"\b{word}\b", lowered):
            return word
    return "none"


def build_state(
    query_id: str,
    query_text: str,
    available: tuple[str, ...],
    degraded: tuple[str, ...] = (),
    linked_entities: tuple[str, ...] = (),
    context_budget: int = 8,
    latency_budget_ms: float = 0.0,
):
    """Construct the router's view of one situation."""
    from .model import MemoryState

    tokens = tokenise(query_text)
    token_set = set(tokens)
    return MemoryState(
        query_id=query_id,
        query_text=query_text,
        query_tokens=len(tokens),
        interrogative=interrogative_of(query_text),
        cue_terms=tuple(tokens),
        locational_signal=_signal(token_set, LOCATIONAL),
        relational_signal=_signal(token_set, RELATIONAL),
        synthesis_signal=_signal(token_set, SYNTHESIS),
        temporal_signal=_signal(token_set, TEMPORAL),
        causal_signal=_signal(token_set, CAUSAL),
        counterfactual_signal=_signal(token_set, COUNTERFACTUAL),
        generality_signal=generality_signal(query_text),
        linked_entities=tuple(linked_entities),
        available_capabilities=tuple(available),
        degraded_capabilities=tuple(degraded),
        context_budget=context_budget,
        latency_budget_ms=latency_budget_ms,
    )


# -- feature vectors for the learned router -------------------------------

FEATURE_NAMES: tuple[str, ...] = (
    "query_tokens_scaled",
    "locational_signal",
    "relational_signal",
    "synthesis_signal",
    "temporal_signal",
    "causal_signal",
    "counterfactual_signal",
    "generality_signal",
    "linked_entity_count_scaled",
    "interrogative_what",
    "interrogative_where",
    "interrogative_why",
    "interrogative_when",
    "interrogative_which",
    "interrogative_who",
    "interrogative_how",
    "has_prior_action",
    "last_evidence_scaled",
    "last_top_score",
    "last_score_margin",
    "disagreement",
)


def feature_vector(state) -> list[float]:
    """Dense features for the classifier router. Order is FEATURE_NAMES."""
    interrogatives = {
        f"interrogative_{word}": 1.0 if state.interrogative == word else 0.0
        for word in INTERROGATIVES
    }
    values = {
        "query_tokens_scaled": min(1.0, state.query_tokens / 20.0),
        "locational_signal": state.locational_signal,
        "relational_signal": state.relational_signal,
        "synthesis_signal": state.synthesis_signal,
        "temporal_signal": state.temporal_signal,
        "causal_signal": state.causal_signal,
        "counterfactual_signal": state.counterfactual_signal,
        "generality_signal": state.generality_signal,
        "linked_entity_count_scaled": min(
            1.0, len(state.linked_entities) / 10.0
        ),
        "has_prior_action": 1.0 if state.actions_taken else 0.0,
        "last_evidence_scaled": min(1.0, state.last_evidence_count / 10.0),
        "last_top_score": state.last_top_score,
        "last_score_margin": state.last_score_margin,
        "disagreement": 1.0 if state.disagreement else 0.0,
        **interrogatives,
    }
    return [float(values[name]) for name in FEATURE_NAMES]


# -- leakage audit -----------------------------------------------------------

# Field names that would give the router the answer rather than the
# question. ``audit_state`` refuses any state object carrying one.
FORBIDDEN_FIELDS: tuple[str, ...] = (
    "family",
    "task_family",
    "expected_sources",
    "expected_state",
    "expected_status",
    "expected_current",
    "expected_historical",
    "superseded_options",
    "temporal_mode",
    "answer",
    "gold",
    "label",
    "oracle",
)


def audit_state(state) -> list[str]:
    """Return the names of any evaluator-only fields present on a state.

    An empty list is the passing result. This runs in the test suite and
    in the router's own health check, because leakage is the failure that
    would make every other number in the chapter meaningless.
    """
    found = []
    for name in FORBIDDEN_FIELDS:
        if hasattr(state, name):
            found.append(name)
    return found
