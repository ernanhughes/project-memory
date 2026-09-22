"""The bounded decision router: a small classifier over dense features.

This is the cheap end of the design space. A multinomial logistic model
over twenty features decides in microseconds, is deterministic, has no
decoding parameters, and cannot produce a malformed answer because its
output space *is* the action space.

The chapter uses it to ask a specific question: does routing need a
language model to read the question, or is routing a bounded decision
problem that a small discriminative model solves just as well? Vendors
are currently selling exactly this claim for decision-only models; the
book tests the architectural claim with its own small model rather than
taking a benchmark on faith.

Implemented from scratch in numpy so the chapter has no new dependency
and the training is inspectable: gradient descent on cross-entropy with
L2, fixed seed, fixed iteration count.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ..capabilities.registry import RAG
from ..state.features import FEATURE_NAMES, feature_vector
from ..state.model import MEDIUM, MemoryAction, MemoryState
from .base import BasePolicy


def _softmax(values: list[float]) -> list[float]:
    peak = max(values) if values else 0.0
    exps = [math.exp(v - peak) for v in values]
    total = sum(exps) or 1.0
    return [e / total for e in exps]


class LogisticRouter:
    """Multinomial logistic regression over the router's feature vector."""

    def __init__(self, labels: list[str], config) -> None:
        self.labels = list(labels)
        self.config = config
        self.weights = [
            [0.0] * (len(FEATURE_NAMES) + 1) for _ in self.labels
        ]

    def _logits(self, features: list[float]) -> list[float]:
        augmented = list(features) + [1.0]  # bias term
        return [
            sum(w * x for w, x in zip(row, augmented))
            for row in self.weights
        ]

    def predict(self, features: list[float]) -> list[float]:
        return _softmax(self._logits(features))

    def fit(self, samples: list[tuple[list[float], str]]) -> dict:
        """Full-batch gradient descent. Deterministic given the config."""
        if not samples:
            return {"trained": False, "reason": "no samples"}
        index = {label: i for i, label in enumerate(self.labels)}
        history: list[float] = []
        n = len(samples)
        for _epoch in range(self.config.epochs):
            gradients = [
                [0.0] * (len(FEATURE_NAMES) + 1) for _ in self.labels
            ]
            loss = 0.0
            for features, label in samples:
                augmented = list(features) + [1.0]
                probabilities = self.predict(features)
                target = index[label]
                loss -= math.log(max(1e-12, probabilities[target]))
                for k in range(len(self.labels)):
                    error = probabilities[k] - (1.0 if k == target else 0.0)
                    for j, x in enumerate(augmented):
                        gradients[k][j] += error * x
            for k in range(len(self.labels)):
                for j in range(len(FEATURE_NAMES) + 1):
                    grad = gradients[k][j] / n
                    if j < len(FEATURE_NAMES):
                        grad += self.config.l2 * self.weights[k][j]
                    self.weights[k][j] -= self.config.learning_rate * grad
            history.append(loss / n)
        return {
            "trained": True,
            "samples": n,
            "labels": list(self.labels),
            "final_loss": round(history[-1], 5),
            "initial_loss": round(history[0], 5),
        }

    def to_dict(self) -> dict:
        return {
            "labels": self.labels,
            "weights": self.weights,
            "feature_names": list(FEATURE_NAMES),
            "model_version": self.config.model_version,
        }

    @classmethod
    def from_dict(cls, payload: dict, config) -> "LogisticRouter":
        router = cls(payload["labels"], config)
        router.weights = payload["weights"]
        return router


class ClassifierPolicy(BasePolicy):
    """Route by argmax over the classifier's distribution."""

    policy_type = "classifier"

    def __init__(self, router: LogisticRouter, config, context_budget: int = 8):
        super().__init__()
        self.router = router
        self.config = config
        self.context_budget = context_budget
        self.policy_version = config.model_version
        self.low_confidence_fallbacks = 0

    def decide(self, state: MemoryState, registry) -> MemoryAction:
        candidates = self.candidates(state, registry)
        features = feature_vector(state)
        probabilities = self.router.predict(features)
        scores = {
            label: probability
            for label, probability in zip(self.router.labels, probabilities)
        }
        # Only choose something that is actually available right now.
        allowed = {
            label: score for label, score in scores.items()
            if label in candidates
        }
        fallback = False
        if not allowed:
            choice, confidence = (
                RAG if RAG in candidates else (candidates[0] if candidates
                                               else "ABSTAIN")
            ), 0.0
            fallback = True
        else:
            choice = max(allowed, key=lambda label: (allowed[label], label))
            confidence = allowed[choice]
            if confidence < self.config.abstain_below:
                self.low_confidence_fallbacks += 1
                choice = RAG if RAG in candidates else choice
                fallback = True
        action = MemoryAction(
            capability=choice,
            retrieval_budget=MEDIUM,
            context_budget=self.context_budget,
            reason="classifier argmax",
        )
        return self.record(
            state, action, candidates,
            scores={k: round(v, 4) for k, v in sorted(scores.items())},
            confidence=round(confidence, 4),
            reason_features=[
                f"{name}={value:.3f}"
                for name, value in zip(FEATURE_NAMES, features)
                if value
            ],
            fallback_used=fallback,
        )

    def manifest(self) -> dict:
        record = super().manifest()
        record.update(
            {
                "model_version": self.config.model_version,
                "epochs": self.config.epochs,
                "learning_rate": self.config.learning_rate,
                "l2": self.config.l2,
                "abstain_below": self.config.abstain_below,
                "labels": list(self.router.labels),
                "low_confidence_fallbacks": self.low_confidence_fallbacks,
            }
        )
        return record


def save_router(router: LogisticRouter, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(router.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def load_router(path: Path, config) -> LogisticRouter:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return LogisticRouter.from_dict(payload, config)
