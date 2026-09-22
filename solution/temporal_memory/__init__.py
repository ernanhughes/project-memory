"""Temporal memory (Chapter 8): ordered transitions between remembered states.

ZeroMQ is transport, not memory. The durable append-only event log is
canonical; current belief is a projection derived by a deterministic
reducer. Queries carry an explicit standpoint (valid_at, known_at).
"""

from .model import EventEnvelope, SCHEMA_VERSION, REDUCER_VERSION
from .log import EventLog
from .reducer import reduce_into, replay, empty_projection
from .query import TemporalEngine, ResolverCondition

__all__ = [
    "EventEnvelope",
    "SCHEMA_VERSION",
    "REDUCER_VERSION",
    "EventLog",
    "reduce_into",
    "replay",
    "empty_projection",
    "TemporalEngine",
    "ResolverCondition",
]
