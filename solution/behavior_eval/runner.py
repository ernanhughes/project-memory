"""Experiment runner: cached calls, repeats, paired comparisons.

Reader identity is fixed per run (default ollama:llama3.1:8b@t0).
Every model response is cached by exact prompt hash, so frozen runs
replay without re-querying. Repeats are paired: same task, same
conditions, repeat index recorded.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from . import contexts as C
from . import graders
from . import prompts as P
from .model import (Action, BehaviorOutcome, BehaviorTask, ProjectWorld,
                    execute, run_actions)

B_CODES = {
    "B0": "required historical information absent from the corpus",
    "B1": "memory present but never retrieved (absent from RAG bundle)",
    "B2": "retrieved but removed by selection/frame",
    "B3": "selected but removed by assembly/budget",
    "B4": "correct context reached reader but behaviour unchanged",
    "B5": "reader used memory but interpreted it incorrectly",
    "B6": "reader followed stale/harmful memory",
    "B7": "correct plan but simulated execution failed",
    "B8": "evaluator/ledger defect (manual flag)",
    "parse-error": "structured actions unparseable",
}


def initial_world(task: BehaviorTask) -> ProjectWorld:
    if task.task_id == "corpus-cleanup":
        return ProjectWorld(facade_contract_active=True,
                            facade_intact=True, docs_state="stale",
                            fixtures_state="stale",
                            callers_migrated=())
    return ProjectWorld()


def score_outcome(task: BehaviorTask, actions: list[Action],
                  answer_text: str, parse_ok: bool, entry: dict,
                  condition: str, repeat: int, reader_name: str,
                  membership=None,
                  no_memory_types: list[str] | None = None
                  ) -> BehaviorOutcome:
    world = run_actions(initial_world(task), actions)
    # task_success is derived (mean of graded dimensions), never graded.
    graded_dims = tuple(d for d in task.applicable if d != "task_success")
    if not parse_ok:
        dims = tuple((d, 0.0) for d in graded_dims)
        task_score: float | None = 0.0
        failures = ("parse-error",)
    else:
        scored = graders.grade(task, actions, world)
        dims = tuple((d, scored.get(d)) for d in graded_dims)
        # task_score averages quality dimensions only; harmful_actions
        # (higher = worse) is reported separately, never averaged away.
        vals = [v for k, v in dims
                if v is not None and k != "harmful_actions"]
        task_score = round(sum(vals) / len(vals), 4) if vals else None
        failures = _attribute(task, actions, world, task_score,
                              membership, no_memory_types)
    return BehaviorOutcome(
        task_id=task.task_id, memory_condition=condition,
        context_hash=entry["context_hash"],
        context_tokens=entry["tokens"],
        memory_ids=tuple(entry["memory_ids"]),
        structured_actions=tuple(a.to_dict() for a in actions),
        answer_text=answer_text, parse_ok=parse_ok,
        dimension_scores=dims, task_score=task_score,
        failure_classes=tuple(failures), repeat_index=repeat,
        reader=reader_name)


def _attribute(task: BehaviorTask, actions: list[Action],
               world: ProjectWorld, task_score: float | None,
               membership=None,
               no_memory_types: list[str] | None = None
               ) -> tuple[str, ...]:
    """Deterministic failure attribution (§60, B0-B8).

    Memory-stage codes (B0-B3) come from frozen membership: corpus,
    C0 bundle, C5 bundle, A6@768 render. Behaviour-stage codes from
    the outcome: B6 harmful action taken; B4 decisive present but
    behaviour identical to no-memory (ignored); B5 behaviour changed
    in the wrong direction (misinterpreted). B7 has no code path in
    a total deterministic executor and is documented, not emitted.
    Only emitted for non-perfect outcomes; clean runs carry no codes.
    """
    if task_score is not None and task_score >= 1.0:
        return ()
    codes: list[str] = []
    if membership is not None:
        for unit in task.decisive_units:
            if unit not in membership["corpus"]:
                codes.append("B0")
            elif unit not in membership["c0"]:
                codes.append("B1")
            elif unit not in membership["c5"]:
                codes.append("B2")
            elif unit not in membership["a6"]:
                codes.append("B3")
    if world.harmful_actions:
        codes.append("B6")
    if no_memory_types is not None and membership is not None:
        same = ([a.action_type for a in actions] == no_memory_types)
        present_here = any(u in membership.get("here", set())
                           for u in task.decisive_units)
        if same and present_here and task.decisive_units:
            codes.append("B4")
        elif not same and (task_score or 0) < 1.0:
            codes.append("B5")
    return tuple(sorted(set(codes)))


def run_condition(task: BehaviorTask, condition: str, entry: dict,
                  ask, reader_name: str, repeat: int = 0,
                  membership=None,
                  no_memory_types: list[str] | None = None
                  ) -> BehaviorOutcome:
    prompt = P.build_prompt(task, entry["context"])
    answer = ask(task, entry, prompt, condition, repeat)
    actions_raw, parse_ok = P.parse_actions(answer, task.action_schema)
    actions = [Action.from_dict(a) for a in actions_raw]
    return score_outcome(task, actions, answer, parse_ok, entry,
                         condition, repeat, reader_name, membership,
                         no_memory_types)


def capped_ask(model: str, host: str, system: str, prompt: str,
               num_predict: int = 1024, timeout: int = 600) -> str:
    """One generation with a bounded output length.

    The shared frozen reader (`context_frames.reader`) is left
    byte-identical: its cache keys and defaults predate this chapter.
    Chapter 12 bounds only its own new prompts, recorded in the
    manifest decoding config. Rationale plus JSON actions fit far
    below the cap; the cap exists so one runaway generation cannot
    stall the suite.
    """
    import json as _json
    import urllib.request as _request
    payload = _json.dumps({
        "model": model, "prompt": prompt, "system": system,
        "stream": False, "options": {"temperature": 0.0, "seed": 7,
                                     "num_predict": num_predict},
    }).encode()
    request = _request.Request(
        f"{host.rstrip('/')}/api/generate", data=payload,
        headers={"Content-Type": "application/json"})
    with _request.urlopen(request, timeout=timeout) as response:
        out = _json.load(response)
    return out.get("response", "").strip()


class ReaderClient:
    """Fixed-identity reader with an exact-prompt disk cache.

    ``cache_salt`` namespaces the cache without changing anything
    else: remote readers (e.g. OpenCode/Muse) pass their full
    request identity (provider, model, reasoning effort,
    temperature) so their rows can never collide with Ollama rows
    for the same prompt. The default ``""`` keeps the Ollama cache
    keys byte-identical to previous runs.
    """

    def __init__(self, model: str, cache_dir: Path, live=None,
                 cache_salt: str = "") -> None:
        self.model = model
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.live = live
        self.calls = 0
        self.hits = 0
        self.cache_salt = cache_salt

    @property
    def name(self) -> str:
        return f"{self.model}@t0"

    def _cache_key(self, prompt: str, repeat: int) -> str:
        parts = [self.model, P.SYSTEM_PROMPT, prompt, str(repeat)]
        if self.cache_salt:
            parts.insert(0, self.cache_salt)
        return hashlib.sha256(
            "\x00".join(parts).encode()).hexdigest()[:40]

    def ask(self, task: BehaviorTask, entry: dict, prompt: str,
            condition: str, repeat: int) -> str:
        key = self._cache_key(prompt, repeat)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            self.hits += 1
            return json.loads(path.read_text())["response"]
        if self.live is None:
            raise RuntimeError("no live reader and cache miss")
        self.calls += 1
        response = self.live(prompt)
        path.write_text(json.dumps(
            {"task": task.task_id, "condition": condition,
             "repeat": repeat, "context_hash": entry["context_hash"],
             "prompt": prompt, "response": response}))
        return response
