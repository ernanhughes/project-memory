"""Project Memory Policy v1: frozen integrated pipeline (capstone).

Frozen decisions (not to be retuned against held-out tasks):

* A6 is NOT part of v1. Grouping, echo collapse, generic redundancy
  reduction, and explicit budgeting are measured but not earned.
* S2 (decisive evidence + source provenance) is the canonical
  assembly rule.
* C3 temporal validity, C4 project scope, and C6 trust admission
  compose in that order; each is imported unchanged.
* C5 contributes no exclusion on history without asserted frame
  uncertainty (pass-through with reason, never silent).
* The C6 derived-from-revoked-source gap stays open (known defect,
  pinned in tests, never laundered through assembly).

Pipeline per task views (deterministic, model-free):

    C3 temporal_filter
      -> C4 scope_filter
      -> C5 pass-through (reason recorded)
      -> C6 trust admission (FULL, no probe metadata)
      -> S2 assembly (decisive + provenance)

POLICY_VERSION = "project-memory-v1", recorded in run manifests.
"""

from __future__ import annotations

POLICY_VERSION = "project-memory-v1"

# Question-type routing: which pipeline stages may govern which
# question class. Follows question semantics, never scores:
#
# * recall (Q1, Q-recall): retrieval + temporal interpretation.
#   Authority must not erase history: preferences and echoes stay
#   visible because "where was it discussed" is about the record,
#   not its standing to direct action.
# * explanatory/state (Q2-Q5): retrieval + temporal. Currency
#   matters (Q4 is validity by definition); trust exclusion does
#   not apply — explanation cites, it does not obey.
# * action/influence (action tasks, Q6 selection, probes): the full
#   v1 pipeline including trust admission and S2 assembly.
# * control (echo/irrelevant): no memory at all. An answer already
#   present in the query must not be displaced by retrieval.
QUESTION_ROUTES = {
    "recall": ("retrieval", "temporal"),
    "explanatory": ("retrieval", "temporal"),
    "action": ("retrieval", "temporal", "scope", "frame", "trust",
               "assembly"),
    "control": (),
}

# Family to route. Q2 straddles recall/explanation in the book, but
# here every Q2 asks for records about a decision (evidence
# lookup), so explanatory fits; recall is reserved for
# discussion-enumeration (Q1) and full-listing (Q-recall) tasks.
FAMILY_ROUTES = {
    "Q1": "recall",
    "Q2": "explanatory",
    "Q3": "explanatory",
    "Q4": "explanatory",
    "Q5": "explanatory",
    "Q-recall": "recall",
    "Q-irr": "control",
    "new-service": "action",
    "action-probe": "action",
}


def route_for(family: str) -> tuple:
    """Pipeline stages for a task family. Unknown families raise:
    routing must be explicit, never defaulted."""
    if family not in FAMILY_ROUTES:
        raise ValueError(f"unrouted family {family!r}")
    return QUESTION_ROUTES[FAMILY_ROUTES[family]]


def routed_admission(task_views: list[dict], world, task,
                     family: str, meta: dict | None = None) -> tuple:
    """Admission honoring the family route. Recall/explanatory apply
    temporal filtering only (no trust exclusion); action applies the
    full integrated pipeline; control admits nothing. Returns
    (views, trace) with the route recorded."""
    from simulator import scope as scope_mod
    from simulator import temporal as temporal_mod
    route = route_for(family)
    trace: dict = {"route": list(route)}
    if route == ():
        trace["control"] = {"kept": 0, "reason": "no-memory-control"}
        return [], trace
    stage = temporal_mod.temporal_filter(task_views, world.ledger,
                                        task.as_of)
    trace["temporal"] = {"kept": len(stage)}
    if "trust" not in route and "scope" not in route:
        return stage, trace
    stage = scope_mod.scope_filter(stage, task.project)
    trace["scope"] = {"kept": len(stage)}
    if "trust" not in route:
        return stage, trace
    kept, verdicts = c6_admitted(stage, world, task, meta)
    trace["trust"] = {
        "kept": len(kept),
        "denied": sorted(
            uid for uid, verdict in verdicts.items()
            if verdict != "admit")}
    return kept, trace


def c6_admitted(task_views: list[dict], world, task,
                meta: dict | None = None) -> tuple[list, dict]:
    """Trust admission over full task views. Returns (admitted,
    verdicts). Identical construction to the C6 measurements."""
    from simulator import trust_gate as tg_mod
    by_display, by_key = {}, {}
    for record in world.ledger.records:
        by_key[record.key] = record
        if record.display_id:
            by_display[record.display_id] = record
        if record.second_display_id:
            by_display[record.second_display_id] = record
    units = tg_mod.units_from_views(task_views, by_display, by_key,
                                    meta or {})
    packet = tg_mod.task_packet(task)
    admits = tg_mod.admit(units, packet, "FULL")
    kept = [v for v in task_views
            if admits.get(v["display_id"]) is not None
            and admits[v["display_id"]].verdict == "admit"]
    return kept, {uid: a.verdict for uid, a in admits.items()}


def integrated_views(task_views: list[dict], world, task,
                     meta: dict | None = None) -> tuple:
    """Full v1 pipeline. Returns (views, trace) with a stage entry
    per layer, including the C5 pass-through reason. Probe metadata
    (revoked/refutes designations) threads into C6 admission only;
    C3/C4/C5 never see it."""
    from simulator import scope as scope_mod
    from simulator import temporal as temporal_mod
    trace: dict = {}
    stage = temporal_mod.temporal_filter(task_views, world.ledger,
                                        task.as_of)
    trace["C3-temporal"] = {
        "kept": len(stage),
        "dropped": sorted(
            {v["display_id"] for v in task_views}
            - {v["display_id"] for v in stage})}
    stage = scope_mod.scope_filter(stage, task.project)
    trace["C4-scope"] = {
        "kept": len(stage),
        "dropped": sorted(
            {v["display_id"] for v in task_views}
            - {v["display_id"] for v in stage})}
    trace["C5-frame"] = {"action": "pass-through",
                         "reason": "no frame uncertainty asserted "
                                   "on history input"}
    kept, verdicts = c6_admitted(stage, world, task, meta)
    trace["C6-trust"] = {
        "kept": len(kept),
        "denied": sorted(
            uid for uid, verdict in verdicts.items()
            if verdict != "admit"),
        "quarantined": sorted(
            uid for uid, verdict in verdicts.items()
            if verdict == "quarantine")}
    trace["S2-assembly"] = {"rule": "decisive-plus-provenance"}
    return kept, trace


def assemble_s2(task_views: list[dict], world, task) -> tuple[list, dict]:
    """Canonical S2 assembly over v1-admitted views: current decision
    display ids plus ledger-first supporting evidence, original
    order. Returns (views, trace)."""
    from simulator import assembly as asm_mod
    from simulator import frames as frames_mod
    admitted, trace = integrated_views(task_views, world, task)
    by_id = {v["display_id"] for v in admitted}
    decisive = {d for d in frames_mod.decisive_ids(
        world, task.topic, task.as_of) if d in by_id}
    dec = [r for r in world.ledger.records
           if r.topic == task.topic and r.kind == "decision"
           and r.date <= task.as_of]
    support: list[str] = []
    if dec:
        best = max(dec, key=lambda r: (r.date, r.key))
        for key in best.supported_by:
            rec = next((x for x in world.ledger.records
                        if x.key == key), None)
            if rec is not None and rec.display_id:
                support.append(rec.display_id)
                if rec.second_display_id:
                    support.append(rec.second_display_id)
    dec_views = [v for v in admitted if v["display_id"] in decisive]
    sup_views = [v for v in admitted
                 if v["display_id"] in support
                 and v["display_id"] not in decisive]
    trace["S2-selected"] = [v["display_id"] for v in dec_views + sup_views]
    return dec_views + sup_views, trace
