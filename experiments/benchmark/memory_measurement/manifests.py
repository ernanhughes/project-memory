"""Frozen-run manifests: reconstructable experiment records.

Any change to a frozen variable creates a new run rather than silently
replacing the old one. The manifest is the instrument's identity device:
it fixes what "the same system" means across a comparison.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from ._version import __version__ as instrument_version
from .scorers import __version__ as scorer_version


@dataclass(frozen=True)
class RunManifest:
    """Everything needed to reconstruct one measurement run."""

    run_id: str
    system_name: str
    condition: str
    corpus_version: str
    task_set_version: str
    generator_seed: int | None = None
    model_identity: str = "unspecified"
    model_version: str = "unspecified"
    prompts: tuple[str, ...] = ()
    embedding_model: str = "unspecified"
    reranker: str = "unspecified"
    chunking_policy: str = "unspecified"
    retrieval_budget: str = "unspecified"
    context_budget: str = "unspecified"
    memory_configuration: str = "unspecified"
    code_commit: str = "unspecified"
    grader_identity: str = "mechanical-only"
    grader_version: str = "unspecified"
    scorer_version: str = scorer_version
    instrument_version: str = instrument_version
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @property
    def manifest_hash(self) -> str:
        digest = hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()
        return digest[:16]

    @classmethod
    def from_dict(cls, data: dict) -> "RunManifest":
        data = dict(data)
        data["prompts"] = tuple(data.get("prompts", ()))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})
