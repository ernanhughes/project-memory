"""Structural health checks for the evidence-lineage layer."""

from __future__ import annotations

from .lineage import LineageGraph


def check_layer(graph: LineageGraph) -> dict:
    """Renderable health report. Structural health is not correctness."""
    report = graph.health()
    lines = [
        f"nodes={report['nodes']} edges={report['edges']} "
        f"claims={report['claims']}",
        f"claims with no lineage: {report['claims_with_no_lineage'] or 'none'}",
        f"dangling edges: {report['dangling_edges'] or 'none'}",
        f"derived without provenance: "
        f"{report['derived_without_provenance'] or 'none'}",
    ]
    return {"report": report, "render": "\n".join(lines)}
