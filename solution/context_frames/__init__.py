"""Context frames (Chapter 10): goal- and project-conditioned context.

Retrieval finds what resembles the query. This layer decides what the
remembered past should contribute to the work being done now, under a
fixed context budget, and records why.
"""

from .model import (ContextBundle, ContextTrace, MemoryUnit, ProjectFrame,
                    WorkFrame, WorkSignal)
from .policy import CONDITIONS, LADDER, POLICY_VERSION, build_context

__all__ = [
    "ContextBundle", "ContextTrace", "MemoryUnit", "ProjectFrame",
    "WorkFrame", "WorkSignal", "CONDITIONS", "LADDER", "POLICY_VERSION",
    "build_context",
]
