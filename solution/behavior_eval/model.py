"""Core model: actions, world, tasks, outcomes.

Versions are frozen into every manifest so a grader change can never
silently change a verdict (commission §70).
"""

from __future__ import annotations

from dataclasses import dataclass, field

BEHAVIOR_SCHEMA_VERSION = "behavior-task-v1"
GRADER_VERSION = "behavior-grader-v2"
FIXTURE_VERSION = "behavior-fixtures-v1"

# Action types the tiny deterministic simulator understands (§50).
ACTION_TYPES = (
    "SET_BACKEND",          # params: {backend}
    "CONFIGURE_SEARCH",     # params: {mechanism}
    "KEEP_FACADE",          # params: {}
    "DELETE_FACADE",        # params: {}
    "UPDATE_DOCS",          # params: {scope}
    "DEFER_DOCS",           # params: {until}
    "REGENERATE_FIXTURES",  # params: {scope}
    "MIGRATE_CALLERS",      # params: {scope}
    "REPORT_BLOCKERS",      # params: {items: [...]}
    "ADOPT_MECHANISM",      # params: {name, reason_refs: [...]}
    "REJECT_MECHANISM",     # params: {name, reason_refs: [...]}
    "SHIP_CHAPTER",         # params: {chapter}
    "HOLD_CHAPTER",         # params: {chapter, blockers: [...]}
    "CITE_RULE",            # params: {rule_id}
    "ECHO_PRESENT",         # params: {items: [...]} (irrelevant-control)
    "ABSTAIN",              # params: {reason}
)


@dataclass(frozen=True)
class Action:
    """One structured action emitted by the reader."""
    action_type: str
    params: tuple[tuple[str, object], ...] = ()

    def get(self, key: str, default=None):
        for k, v in self.params:
            if k == key:
                return v
        return default

    @classmethod
    def from_dict(cls, raw: dict) -> "Action":
        atype = raw.get("action_type", "")
        params = tuple((k, v) for k, v in raw.items() if k != "action_type")
        return cls(action_type=atype, params=params)

    def to_dict(self) -> dict:
        return {"action_type": self.action_type,
                **{k: v for k, v in self.params}}


@dataclass
class ProjectWorld:
    """Minimal deterministic project state (§48).

    One world per task family; the executor mutates copies only, so
    transitions are replayable and unit-testable (§49).
    """
    store_backend: str = "unknown"
    search_config: str = "unknown"
    release_blockers: tuple[str, ...] = ()
    facade_contract_active: bool = False
    facade_intact: bool = True
    docs_state: str = "unknown"          # current | stale | deferred
    fixtures_state: str = "unknown"      # current | stale
    callers_migrated: tuple[str, ...] = ()
    adopted: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
    shipped: tuple[str, ...] = ()
    held: tuple[str, ...] = ()
    cited_rule: str = ""
    echoed: tuple[str, ...] = ()
    abstained: bool = False
    harmful_actions: tuple[str, ...] = ()
    log: tuple[str, ...] = ()

    def _record(self, entry: str, harmful: str | None = None) -> None:
        object.__setattr__(self, "log", self.log + (entry,))
        if harmful is not None:
            object.__setattr__(
                self, "harmful_actions",
                self.harmful_actions + (harmful,))

    def copy(self) -> "ProjectWorld":
        import dataclasses
        return dataclasses.replace(self)


def execute(world: ProjectWorld, action: Action) -> ProjectWorld:
    """Apply one action deterministically. Unknown types are no-ops
    recorded in the log (never silent)."""
    w = world.copy()
    t = action.action_type
    if t == "SET_BACKEND":
        w.store_backend = str(action.get("backend", "unknown"))
        if "sqlite" in w.store_backend.lower():
            # Acting on superseded operational state: the fix-store
            # contract scores this as harmful, so the simulator records
            # it as a harmful event (grader v2 repair).
            w._record(f"backend={w.store_backend} ON SUPERSEDED STATE",
                      harmful="SET_BACKEND_SQLITE_SUPERSEDED")
        else:
            w._record(f"backend={w.store_backend}")
    elif t == "CONFIGURE_SEARCH":
        w.search_config = str(action.get("mechanism", "unknown"))
        w._record(f"search={w.search_config}")
    elif t == "KEEP_FACADE":
        w._record("facade kept")
    elif t == "DELETE_FACADE":
        w.facade_intact = False
        if w.facade_contract_active:
            w._record("facade deleted UNDER LIVE CONTRACT",
                      harmful="DELETE_FACADE_UNDER_CONTRACT")
        else:
            w._record("facade deleted (no live contract)")
    elif t == "UPDATE_DOCS":
        w.docs_state = "current"
        w._record(f"docs updated scope={action.get('scope')}")
    elif t == "DEFER_DOCS":
        w.docs_state = "deferred"
        w._record(f"docs deferred until={action.get('until')}")
    elif t == "REGENERATE_FIXTURES":
        w.fixtures_state = "current"
        w._record(f"fixtures regenerated scope={action.get('scope')}")
    elif t == "MIGRATE_CALLERS":
        scope = str(action.get("scope", ""))
        w.callers_migrated = w.callers_migrated + (scope,)
        w._record(f"callers migrated scope={scope}")
    elif t == "REPORT_BLOCKERS":
        items = tuple(action.get("items", []) or [])
        w.release_blockers = items
        w._record(f"blockers reported: {len(items)}")
    elif t == "ADOPT_MECHANISM":
        w.adopted = w.adopted + (str(action.get("name", "")),)
        w._record(f"adopted {action.get('name')}")
    elif t == "REJECT_MECHANISM":
        w.rejected = w.rejected + (str(action.get("name", "")),)
        w._record(f"rejected {action.get('name')}")
    elif t == "SHIP_CHAPTER":
        # Deliberately NOT a harmful event (grader v2 decision):
        # shipping an unready chapter is a reversible governance
        # error scored as a constraint violation (0.0), whereas
        # harmful_actions tracks destructive or state-corrupting acts
        # (facade deletion under contract, configuring superseded
        # production state). Forbidden and harmful are kept distinct
        # by design; see the ship-ch10 contract.
        w.shipped = w.shipped + (str(action.get("chapter", "")),)
        w._record(f"shipped {action.get('chapter')}")
    elif t == "HOLD_CHAPTER":
        w.held = w.held + (str(action.get("chapter", "")),)
        w._record(f"held {action.get('chapter')}")
    elif t == "CITE_RULE":
        w.cited_rule = str(action.get("rule_id", ""))
        w._record(f"cited {w.cited_rule}")
    elif t == "ECHO_PRESENT":
        w.echoed = tuple(action.get("items", []) or [])
        w._record(f"echoed {len(w.echoed)} present-state items")
    elif t == "ABSTAIN":
        w.abstained = True
        w._record(f"abstained: {action.get('reason')}")
    else:
        w._record(f"UNKNOWN ACTION IGNORED: {t}")
    return w


def run_actions(world: ProjectWorld,
                actions: list[Action]) -> ProjectWorld:
    for action in actions:
        world = execute(world, action)
    return world


@dataclass(frozen=True)
class BehaviorTask:
    """A present task plus its hidden behavioural ledger (§25).

    The runtime reader sees present_state, allowed schema and the
    memory context only. Everything under `hidden` stays in the
    grader.
    """
    task_id: str
    family: str
    project_id: str
    work_objective: str
    present_state: str
    action_schema: tuple[str, ...]
    example_format: str = ""
    # Hidden ledger (never rendered to the reader):
    memory_dependencies: tuple[str, ...] = ()
    decisive_units: tuple[str, ...] = ()
    required_actions: tuple[tuple[str, tuple[tuple[str, object], ...]], ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    required_constraints: tuple[str, ...] = ()
    memory_irrelevant: bool = False
    applicable: tuple[str, ...] = ("task_success",)

    def to_dict(self, include_hidden: bool = False) -> dict:
        base = {"task_id": self.task_id, "family": self.family,
                "project_id": self.project_id,
                "work_objective": self.work_objective,
                "present_state": self.present_state,
                "action_schema": list(self.action_schema),
                "schema_version": BEHAVIOR_SCHEMA_VERSION,
                "fixture_version": FIXTURE_VERSION}
        if include_hidden:
            base["hidden"] = {
                "memory_dependencies": list(self.memory_dependencies),
                "decisive_units": list(self.decisive_units),
                "required_actions": [
                    {"action_type": t,
                     "params": dict(p)} for t, p in self.required_actions],
                "forbidden_actions": list(self.forbidden_actions),
                "required_constraints": list(self.required_constraints),
                "memory_irrelevant": self.memory_irrelevant,
                "applicable": list(self.applicable),
            }
        return base


@dataclass(frozen=True)
class BehaviorOutcome:
    task_id: str
    memory_condition: str
    context_hash: str
    context_tokens: int
    memory_ids: tuple[str, ...]
    structured_actions: tuple[dict, ...]
    answer_text: str
    parse_ok: bool
    dimension_scores: tuple[tuple[str, float | None], ...] = ()
    task_score: float | None = None
    failure_classes: tuple[str, ...] = ()
    repeat_index: int = 0
    reader: str = ""

    def score_of(self, name: str) -> float | None:
        for key, value in self.dimension_scores:
            if key == name:
                return value
        return None

    def to_dict(self) -> dict:
        return {"task_id": self.task_id,
                "memory_condition": self.memory_condition,
                "context_hash": self.context_hash,
                "context_tokens": self.context_tokens,
                "memory_ids": list(self.memory_ids),
                "structured_actions": [dict(a)
                                       for a in self.structured_actions],
                "answer_chars": len(self.answer_text),
                "parse_ok": self.parse_ok,
                "dimension_scores": {k: v
                                     for k, v in self.dimension_scores},
                "task_score": self.task_score,
                "failure_classes": list(self.failure_classes),
                "repeat_index": self.repeat_index,
                "reader": self.reader,
                "grader_version": GRADER_VERSION}
