"""Associative-retrieval configuration. Every field lands in the manifest.

Nothing here is tuned. The defaults are the midpoints of the ranges the
literature reports, and the chapter's experiments are what decide whether
any of them earn their place.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SeedConfig:
    """How a cue enters the graph.

    A bad seed poisons every propagation method downstream, so seed
    quality is measured separately from propagation quality (book §13).
    """

    # Default is lexical. The deterministic fixture has no model server,
    # and the hashing embedder preserves no semantics — a run seeded by
    # it would be a measurement of nothing. Embedding and hybrid seeding
    # are still available and are reported as labelled diagnostics.
    method: str = "lexical"  # lexical | embedding | hybrid | oracle
    top_k: int = 5
    # Minimum seed score to admit a node as a seed at all.
    min_score: float = 0.05
    # Hybrid mixing weight on the lexical component.
    lexical_weight: float = 0.5
    # Embedding provider used for seeding. ``hashing`` keeps the
    # deterministic demo free of network and model dependencies.
    embedding_provider: str = "hashing"
    embedding_model: str = "hashing-256"
    embedding_dimension: int = 256


@dataclass(frozen=True)
class PropagationConfig:
    """Shared propagation budget and the per-strategy parameters."""

    strategy: str = "spreading"  # direct | pagerank | spreading | conditioned
    # Hard bounds. Without these, propagation reaches the whole connected
    # component and 'relevant' stops meaning anything.
    max_hops: int = 3
    max_nodes_expanded: int = 120
    activation_threshold: float = 0.02
    # Spreading activation: fraction of a node's activation retained per
    # step, and the fraction of the remainder passed on.
    retention: float = 0.5
    spread_factor: float = 0.8
    # Divide outgoing activation by the sender's degree (the fan term).
    fan_division: bool = True
    # Lateral inhibition: keep only the strongest ``frontier_top_m``
    # nodes at each step and suppress the rest.
    inhibition: bool = True
    frontier_top_m: int = 7
    inhibition_strength: float = 0.5
    # Personalized PageRank.
    damping: float = 0.85
    pagerank_iterations: int = 30
    pagerank_tolerance: float = 1e-6
    # Query-conditioned propagation: how strongly cue/edge agreement
    # reweights an edge. 0.0 reduces to unconditioned propagation.
    conditioning_strength: float = 1.0
    conditioning_floor: float = 0.1


@dataclass(frozen=True)
class SelectionConfig:
    """What leaves the graph and enters the context.

    Associative search may explore broadly inside the graph, but the
    material handed to a reader stays bounded, so a comparison against
    Chapters 3 and 4 cannot be won by injecting more history.
    """

    max_memories: int = 8
    max_sources: int = 8
    # Final score fusion: activation, direct cue similarity, structural
    # importance. Weights are reported, never hidden inside a ranker.
    activation_weight: float = 0.6
    similarity_weight: float = 0.3
    importance_weight: float = 0.1


@dataclass(frozen=True)
class LearningConfig:
    """Stage B. Off by default; the first result must be interpretable.

    Reinforcement is gated on task outcomes, never on retrieval
    frequency: a pathway used often is not thereby a good pathway (book
    §23, and the experience-following result in the ACL 2026 study).
    """

    enabled: bool = False
    policy_version: str = "assoc-learn-v0.1"
    reinforce_step: float = 0.05
    weaken_step: float = 0.05
    idle_decay: float = 0.01
    min_association: float = 0.05
    max_association: float = 0.95
    # Refuse to strengthen an edge whose evidence is weak, however often
    # a path through it produced a good outcome.
    min_evidence_confidence: float = 0.25
    # Refuse to strengthen an edge with no source provenance at all.
    require_provenance: bool = True


@dataclass(frozen=True)
class AssociativeConfig:
    graph_path: str = "fixtures/assoc/graph-v0.1.json"
    cue_path: str = "fixtures/assoc/cues-v0.1.json"
    seeding: SeedConfig = SeedConfig()
    propagation: PropagationConfig = PropagationConfig()
    selection: SelectionConfig = SelectionConfig()
    learning: LearningConfig = LearningConfig()
    code_commit: str = "unspecified"
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
