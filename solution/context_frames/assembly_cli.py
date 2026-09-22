"""Assembly demo: C5 selection in, bounded working context out."""

from __future__ import annotations

from .assembly_experiments import assemble, load_ch10_inputs


def assembly_demo(task_id: str = "T1-architecture",
                  budget=768) -> str:
    inputs = load_ch10_inputs()
    lines = [f"TASK {task_id}  BUDGET {budget} estimated tokens",
             ""]
    for condition in ("A0-raw", "A6-composed", "CO-content",
                      "CO-auditable", "C6-ch10"):
        r = assemble(task_id, condition, budget, inputs)
        lines.append(
            f"{condition}: required_recall={r['required_recall']} "
            f"useful={r['useful_recall']} "
            f"counted={r['counted_tokens']} "
            f"rendered={r['rendered_tokens']} "
            f"over_budget={r['over_budget']} "
            f"contra={r['contradiction_preservation']} "
            f"licence={r['licence_preservation']}")
    lines.append("")
    r = assemble(task_id, "A6-composed", budget, inputs)
    lines.append("A6 TRACE:")
    for op in r["trace"]["operations"]:
        lines.append(f"  {op}")
    lines.append("")
    lines.append("A6 RENDER (head):")
    lines.append(r["rendered_text"][:1200])
    return "\n".join(lines)


if __name__ == "__main__":
    print(assembly_demo())
