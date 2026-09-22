"""The generative router: a language model choosing from a bounded schema.

The model is asked for a decision, not for prose. It receives the
question and the capability descriptors, and must answer with one JSON
object drawn from a closed action space. Everything that could make the
decision irreproducible is frozen — model, prompt, temperature, seed —
and the prompt hash goes into the manifest, because a router is control
infrastructure and control infrastructure that cannot be reproduced
cannot be debugged.

Two failure modes are handled explicitly rather than hidden. A malformed
response falls back to the cheapest capability and is *recorded* as a
fallback, so schema failures show up in the results instead of silently
becoming "the router chose RAG". And because the same query can be asked
repeatedly, route variance is measurable: ``measure_variance`` runs one
state several times and reports how often the answer changes.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request

from ..capabilities.registry import RAG
from ..state.model import BUDGET_TIERS, MEDIUM, MemoryAction, MemoryState
from .base import BasePolicy

PROMPT_TEMPLATE = """\
You are the memory controller for a system that answers questions about \
a software project's recorded history. Choose which memory mechanism \
should run for this question.

Available mechanisms:
{capabilities}

Question:
{question}

Reply with one JSON object and nothing else:
{{"capability": "<one of {ids}>", "budget": "<LOW|MEDIUM|HIGH>", \
"reason": "<at most 12 words>"}}
"""


def _extract_json(raw: str) -> dict | None:
    """Pull the first JSON object out of a model response."""
    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class LLMPolicy(BasePolicy):
    """Bounded structured choice from a fixed local model."""

    policy_type = "llm"

    def __init__(self, config, context_budget: int = 8) -> None:
        super().__init__()
        self.config = config
        self.context_budget = context_budget
        self.policy_version = (
            f"llm:{config.model}:{config.prompt_version}"
        )
        self.schema_failures = 0
        self.calls = 0

    def prompt_hash(self) -> str:
        return hashlib.sha1(PROMPT_TEMPLATE.encode()).hexdigest()[:12]

    def _ask(self, prompt: str) -> str:
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "seed": self.config.seed,
                "num_predict": self.config.max_tokens,
            },
        }
        request = urllib.request.Request(
            f"{self.config.ollama_host.rstrip('/')}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response).get("response", "")

    def decide(self, state: MemoryState, registry) -> MemoryAction:
        candidates = self.candidates(state, registry)
        descriptions = "\n".join(
            registry.get(cid).describe() for cid in candidates
        )
        prompt = PROMPT_TEMPLATE.format(
            capabilities=descriptions,
            question=state.query_text,
            ids="|".join(candidates),
        )
        self.calls += 1
        try:
            raw = self._ask(prompt)
        except Exception as exc:
            return self._fallback(
                state, candidates, f"router call failed: {exc}"[:120]
            )
        parsed = _extract_json(raw)
        if parsed is None:
            self.schema_failures += 1
            return self._fallback(
                state, candidates, "malformed router response"
            )
        capability = str(parsed.get("capability", "")).strip().upper()
        if capability not in candidates:
            self.schema_failures += 1
            return self._fallback(
                state, candidates,
                f"router named an unavailable capability: {capability!r}",
            )
        budget = str(parsed.get("budget", MEDIUM)).strip().upper()
        if budget not in BUDGET_TIERS:
            budget = MEDIUM
        action = MemoryAction(
            capability=capability,
            retrieval_budget=budget,
            context_budget=self.context_budget,
            reason=str(parsed.get("reason", ""))[:120],
        )
        return self.record(
            state, action, candidates, confidence=0.0,
            reason_features=[f"llm:{self.config.model}",
                             f"prompt:{self.prompt_hash()}"],
            notes="confidence unavailable: the model reports none",
        )

    def _fallback(self, state, candidates, why: str) -> MemoryAction:
        choice = RAG if RAG in candidates else (
            registry_cheapest(candidates) or "ABSTAIN"
        )
        action = MemoryAction(
            capability=choice,
            retrieval_budget=MEDIUM,
            context_budget=self.context_budget,
            reason=f"fallback: {why}",
        )
        return self.record(
            state, action, candidates, confidence=0.0,
            reason_features=["fallback", why], fallback_used=True,
        )

    def manifest(self) -> dict:
        record = super().manifest()
        record.update(
            {
                "model": self.config.model,
                "temperature": self.config.temperature,
                "seed": self.config.seed,
                "prompt_version": self.config.prompt_version,
                "prompt_sha1": self.prompt_hash(),
                "calls": self.calls,
                "schema_failures": self.schema_failures,
            }
        )
        return record


def registry_cheapest(candidates):
    return sorted(candidates)[0] if candidates else None


def measure_variance(policy, state, registry, repeats: int = 5) -> dict:
    """How often does the same state produce the same route?

    A deterministic router scores 1.0 here by construction. A generative
    one has to earn it, and the number belongs in the results rather than
    in an assumption.
    """
    choices: list[str] = []
    for _ in range(repeats):
        choices.append(policy.decide(state, registry).capability)
    modal = max(set(choices), key=choices.count)
    return {
        "repeats": repeats,
        "choices": choices,
        "modal_choice": modal,
        "agreement": choices.count(modal) / repeats,
    }
