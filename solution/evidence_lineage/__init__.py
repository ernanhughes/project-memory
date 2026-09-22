"""Evidence lineage layer (Chapter 7).

Provenance as maintained dependency information: derived claims keep
explicit links to the evidence that licenses them, so that later
evidence knows what to attack.

Two graphs share node identities but never semantics:

* the memory/semantic graph (Chapters 4-5): entities and relations
  such as ``Bill WORKS_ON ProjectAlpha``;
* the evidence/lineage graph (this layer): ``SUPPORTED_BY`` (evidential),
  ``DERIVED_FROM`` (lineage), ``ECHO_OF`` (restatement) and ``REFUTES``.

Submodules are deliberately consolidated: no abstraction file exists
without a measurable use.
"""

from .config import EvidenceConfig
from .lineage import EdgeKind, LineageGraph, NodeKind
from .claims import Claim, extract_claims_c0, extract_claims_c1, extract_claims_c2

__all__ = [
    "EvidenceConfig",
    "EdgeKind",
    "LineageGraph",
    "NodeKind",
    "Claim",
    "extract_claims_c0",
    "extract_claims_c1",
    "extract_claims_c2",
]
