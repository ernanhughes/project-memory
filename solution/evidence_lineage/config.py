"""Evidence-lineage configuration. Every field lands in the run manifest.

A support graph built with a new extractor is a different derived
artifact, so extractor identity and version are part of the config.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EvidenceConfig:
    layer_version: str = "evidence-lineage-v0.1"
    corpus_version: str = "ch7-fixture-v0.1"
    claim_extractor: str = "c2-claimify-inspired-v0.1"
    support_verifier: str = "ledger-deterministic-v0.1"
    echo_threshold: float = 0.55
    code_commit: str = "unspecified"
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
