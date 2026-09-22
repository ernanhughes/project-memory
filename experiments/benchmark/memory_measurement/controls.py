"""Baselines and controls for the Measurement Instrument.

A memory claim is comparative: behaviour with a retained past against
behaviour without it, with controls that separate content-caused
improvement from longer-context or formatting effects.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Condition:
    """One experimental condition applied to the same task set."""

    name: str
    description: str


NO_MEMORY = Condition(
    name="no-memory",
    description="System receives the task with no historical memory.",
)
FULL_HISTORY = Condition(
    name="full-history",
    description="System receives as much raw history as feasible.",
)
RANDOM_HISTORY = Condition(
    name="random-history",
    description="System receives irrelevant history matched for size.",
)
SCRAMBLED_HISTORY = Condition(
    name="scrambled-history",
    description="Token quantity and formatting preserved; historical "
    "content destroyed. Separates content-caused improvement from "
    "longer-context effects.",
)
ORACLE_MEMORY = Condition(
    name="oracle-memory",
    description="System receives exactly the memory the task needs. "
    "Approximate ceiling for selection, independent of retrieval.",
)
LEXICAL_RETRIEVAL = Condition(
    name="lexical-retrieval",
    description="Keyword retrieval over the rendered history.",
)
EMBEDDING_TOP_K = Condition(
    name="embedding-top-k",
    description="Embedding retrieval, top-k passages, no reranking.",
)
EMBEDDING_RERANKED = Condition(
    name="embedding-reranked",
    description="Embedding retrieval plus reranking before selection.",
)

STANDARD_CONDITIONS: tuple[Condition, ...] = (
    NO_MEMORY,
    LEXICAL_RETRIEVAL,
    EMBEDDING_TOP_K,
    EMBEDDING_RERANKED,
    FULL_HISTORY,
    SCRAMBLED_HISTORY,
    ORACLE_MEMORY,
)

# Adversarial conditions grow with the book; v0.1 names the first two.
STALE_MEMORY_ADVERSARY = Condition(
    name="stale-memory-adversary",
    description="A plausible but superseded memory is injected; the "
    "system should prefer current state.",
)
DISTRACTOR_MEMORY_ADVERSARY = Condition(
    name="distractor-memory-adversary",
    description="Relevant-looking but incorrect history is injected; "
    "the system should not be diverted.",
)


def memory_delta(score_with_memory: float, score_without_memory: float) -> float:
    """Behavioural delta attributable to memory on one metric."""
    return score_with_memory - score_without_memory


FROZEN_VARIABLES: tuple[str, ...] = (
    "corpus_version",
    "generator_seed",
    "task_set_version",
    "model_identity",
    "model_version",
    "prompts",
    "embedding_model",
    "reranker",
    "chunking_policy",
    "retrieval_budget",
    "context_budget",
    "memory_configuration",
    "code_commit",
    "configuration",
    "grader_identity",
    "grader_version",
    "scorer_version",
)
