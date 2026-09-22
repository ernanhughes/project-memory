"""Memory Nexus configuration. Every field lands in the run manifest.

Control state and memory state are kept apart on purpose (chapter section
"Policy state is not memory state"). Everything here describes *how the
system decides*, never *what the project remembers*: replacing a policy
must never look like the project having changed its mind.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field

from .evaluation.utility import UtilityWeights


@dataclass(frozen=True)
class ReaderConfig:
    """The reader, held fixed across capabilities in Stage A."""

    provider: str = "ollama"
    model: str = "llama3.1:8b"
    temperature: float = 0.0
    ollama_host: str = "http://localhost:11434"


@dataclass(frozen=True)
class RouterModelConfig:
    """The generative router, when one is used.

    Frozen model, frozen prompt, temperature zero, and the prompt hash in
    the manifest: a stochastic router is still control infrastructure, and
    route variance is measured rather than assumed away.
    """

    model: str = "llama3.1:8b"
    temperature: float = 0.0
    seed: int = 0
    max_tokens: int = 160
    ollama_host: str = "http://localhost:11434"
    prompt_version: str = "nexus-router-prompt-v0.1"


@dataclass(frozen=True)
class ClassifierConfig:
    """The bounded decision router.

    A small multinomial logistic model over dense features, trained
    offline on the measured matrix. It is deterministic, has no decoding
    parameters, and answers in microseconds — the cheap end of the design
    space the chapter tests against a generative router.
    """

    epochs: int = 400
    learning_rate: float = 0.5
    l2: float = 0.01
    seed: int = 0
    abstain_below: float = 0.0  # fall back to RAG under this confidence
    model_version: str = "nexus-classifier-v0.1"


@dataclass(frozen=True)
class ControllerConfig:
    """Sequential control: budgets and the guards that stop loops."""

    max_actions: int = 3
    max_cost_units: float = 20.0
    max_latency_ms: float = 600_000.0
    # A capability may not be invoked twice in one episode. Without this
    # a cheap-then-specialist ladder can oscillate indefinitely.
    forbid_repeat_capability: bool = True
    stop_policy_version: str = "nexus-stop-v0.1"


@dataclass(frozen=True)
class NexusConfig:
    registry_version: str = "nexus-caps-v0.1"
    task_set_version: str = "nexus-routing-tasks-v0.1"
    corpus_version: str = "ch3-fixture-v0.1"
    reader: ReaderConfig = ReaderConfig()
    router_model: RouterModelConfig = RouterModelConfig()
    classifier: ClassifierConfig = ClassifierConfig()
    controller: ControllerConfig = ControllerConfig()
    utility: UtilityWeights = UtilityWeights()
    context_budget: int = 8
    code_commit: str = "unspecified"
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_env(cls, **overrides) -> "NexusConfig":
        base: dict = {}
        reader_model = os.environ.get("MEMORY_NEXUS_READER")
        if reader_model:
            base["reader"] = ReaderConfig(model=reader_model)
        router_model = os.environ.get("MEMORY_NEXUS_ROUTER_MODEL")
        if router_model:
            base["router_model"] = RouterModelConfig(model=router_model)
        base.update(overrides)
        return cls(**base)
