"""Behavioural evaluation for Chapter 12.

Measures whether project memory changes what the system does, not
whether it can talk about the past. Consumes frozen contexts, runs a
fixed reader, scores structured actions deterministically.
"""

from .model import (
    BEHAVIOR_SCHEMA_VERSION,
    FIXTURE_VERSION,
    GRADER_VERSION,
)

__all__ = [
    "BEHAVIOR_SCHEMA_VERSION",
    "FIXTURE_VERSION",
    "GRADER_VERSION",
]
