"""Action tasks (T1): one family fully, framework for the rest.

Family `new-service` (respect current architecture): propose the
implementation target for a new service. Built per topic holding a
currently-valid positive target decision at the task cut. Rejection
topics ("Do not introduce X") yield no task: there is no positive
target to propose, and inventing one would corrupt the contract.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskPacket:
    task_id: str
    family: str
    topic: str
    text: str
    as_of: str


TASK_CUT = "2025-06-30"


def build_tasks(world, topics: list[str]) -> list[TaskPacket]:
    """One new-service task per topic with a parseable current target."""
    tasks = []
    for topic in sorted(topics):
        target = world.current_target(topic)
        if not target:
            continue
        slug = "".join(c if c.isalnum() else "-" for c in topic.lower())
        slug = "-".join(p for p in slug.split("-") if p)[:40]
        tasks.append(TaskPacket(
            task_id=f"task-new-service-{slug}",
            family="new-service",
            topic=topic,
            text=(f"Add a new service that needs {topic}. "
                  f"Propose the implementation target."),
            as_of=world.as_of))
    return tasks
