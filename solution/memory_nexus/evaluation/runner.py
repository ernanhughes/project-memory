"""Building the task-by-capability matrix against the live systems.

Resumable by construction. Each cell is written to a cache file keyed by
the frozen variables, so a run that is interrupted — or that deliberately
excludes an expensive capability on the first pass — can be continued
without repeating work that cost twenty-six minutes a query.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
INSTRUMENT_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark"
for _candidate in (str(SOLUTION_ROOT), str(INSTRUMENT_ROOT)):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from ..state.features import build_state  # noqa: E402
from ..state.model import MEDIUM, MemoryAction  # noqa: E402
from .matrix import CapabilityMatrix, MatrixCell, cache_key, run_cell  # noqa: E402

CACHE_ROOT = SOLUTION_ROOT / "fixtures" / "nexus" / "matrix-cache"


def frozen_context(config, registry) -> dict:
    """Everything whose change should invalidate a measured cell."""
    return {
        "corpus_version": config.corpus_version,
        "task_set_version": config.task_set_version,
        "reader_model": config.reader.model,
        "reader_temperature": config.reader.temperature,
        "registry_version": registry.version,
        "context_budget": config.context_budget,
    }


def state_builder_for(registry, config, graph_system=None):
    """Build router state for a task without touching evaluator fields."""

    def build(task):
        linked: tuple[str, ...] = ()
        if graph_system is not None:
            try:
                from graph_memory.evaluation.adapter import link_entities

                linked = tuple(
                    link_entities(task.prompt, graph_system.snapshot)
                )
            except Exception:
                linked = ()
        return build_state(
            query_id=task.task_id,
            query_text=task.prompt,
            available=tuple(registry.available_ids()),
            degraded=tuple(registry.degraded_ids()),
            linked_entities=linked,
            context_budget=config.context_budget,
        )

    return build


def build_matrix(
    config,
    registry,
    systems,
    tasks,
    reader,
    capabilities: list[str] | None = None,
    task_ids: list[str] | None = None,
    cache_root: Path | None = None,
    progress=None,
) -> CapabilityMatrix:
    """Run every requested (task, capability) pair, resuming from cache."""
    cache_root = Path(cache_root or CACHE_ROOT)
    cache_root.mkdir(parents=True, exist_ok=True)
    context = frozen_context(config, registry)
    wanted_caps = capabilities or registry.available_ids()
    wanted_tasks = [
        task for task in tasks
        if task_ids is None or task.task_id in task_ids
    ]
    matrix = CapabilityMatrix(
        manifest={
            "frozen": context,
            "registry": registry.manifest(),
            "utility": config.utility.to_dict(),
            "capabilities_run": sorted(wanted_caps),
            "tasks_run": [t.task_id for t in wanted_tasks],
        }
    )
    build_state_fn = state_builder_for(
        registry, config, systems.graph_system
    )
    action = MemoryAction(
        capability="", retrieval_budget=MEDIUM,
        context_budget=config.context_budget,
    )
    for task in wanted_tasks:
        for capability_id in sorted(wanted_caps):
            if capability_id not in registry:
                continue
            key = cache_key(task.task_id, capability_id, context)
            cached = cache_root / f"{key}.json"
            if cached.exists():
                matrix.put(
                    MatrixCell.from_dict(
                        json.loads(cached.read_text(encoding="utf-8"))
                    )
                )
                if progress:
                    progress(task.task_id, capability_id, "cached")
                continue
            started = time.perf_counter()
            import dataclasses

            cell = run_cell(
                task=task,
                capability=registry.get(capability_id),
                reader=reader,
                history_source_ids=systems.history_source_ids,
                state_builder=build_state_fn,
                action=dataclasses.replace(action, capability=capability_id),
            )
            cached.write_text(
                json.dumps(cell.to_dict(), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            matrix.put(cell)
            if progress:
                progress(
                    task.task_id,
                    capability_id,
                    f"ran in {time.perf_counter() - started:.1f}s",
                )
    return matrix


def load_matrix(
    config, registry, tasks, cache_root: Path | None = None
) -> CapabilityMatrix:
    """Assemble whatever cells the cache already holds."""
    cache_root = Path(cache_root or CACHE_ROOT)
    context = frozen_context(config, registry)
    matrix = CapabilityMatrix(
        manifest={"frozen": context, "registry": registry.manifest(),
                  "utility": config.utility.to_dict(), "source": "cache"}
    )
    for task in tasks:
        for capability_id in registry.ids():
            cached = cache_root / (
                f"{cache_key(task.task_id, capability_id, context)}.json"
            )
            if cached.exists():
                matrix.put(
                    MatrixCell.from_dict(
                        json.loads(cached.read_text(encoding="utf-8"))
                    )
                )
    return matrix
