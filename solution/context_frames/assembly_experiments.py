"""Chapter 14 suite: frozen C5 selection in, assembly variants out.

Primary experiment freezes Chapter 10 C5 bundles and varies only
assembly. Chapter 10 C6 is an external comparison. Reader scoring uses
the Chapter 10 key-claim scorer when a reader is available; the
headline result is evidence preservation at matched cost.
"""

from __future__ import annotations

import time

from . import assembly as A
from . import fixtures as fx
from .assembly import (
    AssemblyTrace,
    BUDGETS,
    build_ledger,
    count_rendered,
    load_ch10_inputs,
    op_dedup,
    op_drop,
    op_group,
    op_mark,
    op_order,
    render,
)
from .model import estimate_tokens

CONDITIONS = ("A0-raw", "A1-order", "A2-dedup", "A3-group", "A4-mark",
              "A5-drop", "A6-composed", "CO-content", "CO-auditable",
              "C6-ch10", "empty", "random-drop")


def _prefs(task_id: str, traces: dict) -> tuple[tuple[str, ...], str, str]:
    """Frame preferences for runtime ordering (no hidden labels)."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent.parent
    frames_path = (root / "experiments" / "benchmark" / "runs"
                   / "ch10-20260920T163314Z-context-frames"
                   / "project-frames.json")
    frames = json.loads(frames_path.read_text())
    trace = traces[task_id]
    wf = trace.get("work_frame", "")
    wt = None
    for t in fx.all_tasks():
        if t.task_id == task_id:
            wt = t.work_frame.work_type
            project = t.work_frame.project_id
            objective = t.work_frame.objective
            query = t.query
            as_of = trace.get("as_of", "")
            ledger = dict(t.ledger)
            break
    table = {}
    for pid, f in frames.items():
        if pid == project:
            table = f.get("evidence_preferences", {})
            break
    prefs = tuple(table.get(wt, table.get("default", ())))
    return prefs, query, objective, as_of, ledger, project


def assemble(task_id: str, condition: str, budget, inputs) -> dict:
    """Run one assembly condition over the frozen C5 set."""
    started = time.perf_counter()
    units, tasks, bundles, traces = inputs
    prefs, query, objective, as_of, ledger, project = _prefs(task_id,
                                                             traces)
    trace = AssemblyTrace(task_id=task_id, condition=condition,
                          budget=budget)
    c5 = bundles["C5"][task_id]
    trace.log("input", source="ch10-C5-frozen",
              admitted_members=c5_members(c5),
              bundle_tokens=c5["bundle_tokens"])
    if condition == "empty":
        text = render([], query, objective, as_of)
        return _finish(task_id, condition, budget, [], text, trace,
                       started, units, tasks[task_id], ledger, project,
                       as_of, c5)
    if condition == "C6-ch10":
        c6 = bundles["C6"][task_id]
        rows = A._working_set(c6, units, traces.get(task_id), prefs)
        text = render(rows, query, objective, as_of)
        out = _finish(task_id, condition, budget, rows, text, trace,
                      started, units, tasks[task_id], ledger, project,
                      as_of, c5, external=True)
        # C6 items are coalesced: folded members share representative
        # text, so recomputed member-text sums overcount. The frozen
        # bundle figure is the comparable one.
        out["counted_tokens"] = c6["bundle_tokens"]
        return out
    if condition in ("CO-content", "CO-auditable"):
        # Oracle ceilings load the frozen CO bundles directly. Rebuilding
        # the oracle from C5-admitted members would conflate selection
        # loss with assembly loss: the ceiling must be what the ledger
        # permits, not what C5 happened to admit.
        co = bundles["CO"][task_id]
        co_rows = A._working_set(co, units, traces.get(task_id), prefs)
        trace.log("input", source="ch10-CO-frozen",
                  admitted_members=c5_members(co),
                  bundle_tokens=co["bundle_tokens"])
        if condition == "CO-auditable":
            # The auditable oracle also carries what content-minimum
            # drops: unresolved disagreements, derived-loop licence
            # bearers (from the C5 set where the CO set omits them),
            # and the temporal notes that mark superseded history. A
            # content oracle that silently drops contradiction or
            # licences is not a fair ceiling.
            have = {r["unit_id"] for r in co_rows}
            c5_rows = A._working_set(c5, units, traces.get(task_id),
                                     prefs)
            extra = [r for r in c5_rows
                     if r["unit_id"] not in have
                     and (r["evidence_role"] == "refutes"
                          or r["open_loop"])]
            co_rows = co_rows + extra
            trace.log("auditable-additions",
                      added=[r["unit_id"] for r in extra])
            co_rows = op_mark(co_rows, trace, as_of)
        text = render(co_rows, query, objective, as_of)
        return _finish(task_id, condition, budget, co_rows, text,
                       trace, started, units, tasks[task_id], ledger,
                       project, as_of, c5, oracle=True)
    rows = A._working_set(c5, units, traces.get(task_id), prefs)
    if condition == "A0-raw":
        text = render(rows, query, objective, as_of, structured=False)
    elif condition == "A1-order":
        rows = op_order(rows, trace, "evidence-first")
        text = render(rows, query, objective, as_of, structured=False)
    elif condition == "A2-dedup":
        rows = op_dedup(rows, trace)
        text = render(rows, query, objective, as_of, structured=False)
    elif condition == "A3-group":
        rows = op_dedup(rows, trace)
        rows = op_group(rows, trace)
        text = render(rows, query, objective, as_of)
    elif condition == "A4-mark":
        rows = op_mark(rows, trace, as_of)
        text = render(rows, query, objective, as_of)
    elif condition in ("A5-drop", "A6-composed", "random-drop"):
        if condition == "A6-composed":
            rows = op_order(rows, trace, "evidence-first")
            rows = op_dedup(rows, trace)
            rows = op_group(rows, trace)
            rows = op_mark(rows, trace, as_of)
        rows = op_drop(rows, trace, budget, len(prefs),
                       random_drop=(condition == "random-drop"))
        text = render(rows, query, objective, as_of)
    else:
        raise ValueError(f"unknown condition {condition!r}")
    return _finish(task_id, condition, budget, rows, text, trace,
                   started, units, tasks[task_id], ledger, project,
                   as_of, c5)


def c5_members(bundle: dict) -> list[str]:
    out = []
    for item in bundle.get("items", ()):
        out.extend(item.get("members", ()))
    return out


def _finish(task_id, condition, budget, rows, text, trace, started,
            units, task, ledger, project, as_of, c5,
            external=False, oracle=False) -> dict:
    present = {r["unit_id"] for r in rows}
    present |= {u for r in rows for u in r.get("represents", [])}
    must = {u for u, lab in ledger.items() if lab == "MUST"}
    should = {u for u, lab in ledger.items() if lab == "SHOULD"}
    harmful = {u for u, lab in ledger.items() if lab == "HARMFUL"}
    counted = sum(r["tokens"] for r in rows)
    rendered = count_rendered(text)
    # Support-group satisfaction from frozen claim groups.
    groups: dict[str, list[str]] = {}
    for uid in c5_members(c5):
        u = units.get(uid)
        if u is not None and u.claim_key:
            groups.setdefault(u.claim_key, []).append(uid)
    sat, conj_break, alt_waste = 0, 0, 0
    for key, members in groups.items():
        hit = [m for m in members if m in present]
        if hit:
            sat += 1
        primaries = [m for m in members
                     if units[m].evidence_role != "echo"
                     and not units[m].echo_of] if all(
                         m in units for m in members) else members
        if len(primaries) > 1 and hit and len(hit) < len(primaries):
            conj_break += 1
        if len(primaries) <= 1 and len(hit) > 1:
            alt_waste += 1
    # Contradiction / temporal / licence preservation.
    refutes_c5 = [u for u in c5_members(c5)
                  if u in units and units[u].evidence_role == "refutes"]
    refutes_kept = [u for u in refutes_c5 if u in present]
    superseded_c5 = [u for u in c5_members(c5)
                     if u in units and units[u].valid_until is not None]
    superseded_kept = [u for u in superseded_c5 if u in present]
    loops_c5 = [u for u in c5_members(c5)
                if u in units and units[u].open_loop]
    loops_kept = [u for u in loops_c5 if u in present]
    stale_live = [u for u in superseded_kept
                  if not any(op.get("operation") == "mark"
                             for op in trace.operations)]
    out_scope = [u for u in present
                 if u in units and units[u].project_id != project]
    echoes = [u for u in present
              if u in units and (units[u].evidence_role == "echo"
                                 or units[u].echo_of)]
    trace.latency_ms = (time.perf_counter() - started) * 1000.0
    trace.items = [{"unit_id": r["unit_id"], "state": r["state"],
                    "reason": r["reason"],
                    "budget_before": r["budget_before"],
                    "budget_after": r["budget_after"],
                    "tokens": r["tokens"],
                    "represents": r.get("represents", []),
                    "marks": r.get("marks", [])} for r in rows]
    budget_num = budget if isinstance(budget, int) else counted
    return {
        "task_id": task_id, "condition": condition, "budget": budget,
        "present": sorted(present),
        "required_recall": _div(len(present & must), len(must)),
        "useful_recall": _div(len(present & (must | should)),
                              len(must | should)),
        "harmful_admission": _div(len(present & harmful),
                                  len(present)),
        "cross_project_leakage": _div(len(out_scope), len(present)),
        "redundancy_rate": _div(len(echoes), len(present)),
        "group_satisfaction": _div(sat, len(groups)),
        "conjunctive_breakage": conj_break,
        "alternative_waste": alt_waste,
        "contradiction_preservation": _div(len(refutes_kept),
                                          len(refutes_c5)),
        "temporal_marked": [u for u in superseded_kept],
        "stale_unmarked": stale_live,
        "licence_preservation": _div(len(loops_kept), len(loops_c5)),
        "counted_tokens": counted,
        "rendered_tokens": rendered,
        "over_budget": (isinstance(budget, int)
                        and counted > budget),
        "rendered_text": text,
        "trace": trace.to_dict(),
        "external": external, "oracle": oracle,
    }


def _div(a: int, b: int):
    return round(a / b, 4) if b else None


def run_suite(budgets: tuple = BUDGETS, inputs=None,
              reader=None) -> dict:
    """Full suite: every task x condition x budget (evidence only)."""
    import hashlib
    if inputs is None:
        inputs = load_ch10_inputs()
    units, tasks, bundles, traces = inputs
    task_ids = sorted(bundles["C5"].keys())
    out: dict = {"suite": "E-14-context-assembly",
                 "assembly_version": A.ASSEMBLY_VERSION,
                 "drop_policy_version": A.DROP_POLICY_VERSION,
                 "render_version": A.RENDER_VERSION,
                 "source_run": "ch10-20260920T163314Z-context-frames",
                 "selection_input": "C5",
                 "budgets": list(budgets),
                 "conditions": {},
                 "reader": None}
    for condition in CONDITIONS:
        by_budget = {}
        for budget in budgets:
            rows = [assemble(t, condition, budget, inputs)
                    for t in task_ids]
            by_budget[str(budget)] = {
                "tasks": [{k: v for k, v in r.items()
                            if k not in ("rendered_text", "trace")}
                           for r in rows],
                "mean": _mean(rows),
                "traces": {r["task_id"]: r["trace"] for r in rows},
                "renders": {r["task_id"]: r["rendered_text"]
                             for r in rows},
            }
        out["conditions"][condition] = by_budget
    payload = str(sorted(task_ids)).encode()
    out["fixture_digest"] = hashlib.sha256(payload).hexdigest()[:16]
    # Backtest: v2-echo-first drop revision vs frozen v1.
    out["backtest"] = _backtest(inputs)
    return out


def _mean(rows: list[dict]) -> dict:
    def avg(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return round(sum(vals) / len(vals), 4) if vals else None
    return {
        "tasks": len(rows),
        "required_recall": avg("required_recall"),
        "useful_recall": avg("useful_recall"),
        "harmful_admission": avg("harmful_admission"),
        "cross_project_leakage": avg("cross_project_leakage"),
        "redundancy_rate": avg("redundancy_rate"),
        "group_satisfaction": avg("group_satisfaction"),
        "contradiction_preservation": avg("contradiction_preservation"),
        "licence_preservation": avg("licence_preservation"),
        "counted_tokens": round(
            sum(r["counted_tokens"] for r in rows) / len(rows), 1),
        "rendered_tokens": round(
            sum(r["rendered_tokens"] for r in rows) / len(rows), 1),
        "over_budget_tasks": sum(1 for r in rows if r["over_budget"]),
    }


def _backtest(inputs) -> dict:
    """One candidate drop revision, replayed over the whole suite.

    v2-drop-refutes-first treats contradiction as ordinary budget
    weight — the tempting repair when a long dissent crowds out
    supporting evidence. Primary: required recall at budget 512 for
    A6. Gates: harmful/stale no increase, contradiction and licence
    no regression. Expected: rejected on a contradiction breach. A
    protect-outside variant was also tried; it moved recall +0.03 at
    identical cost and was left unpromoted as noise, recorded here so
    the suite shows its work.
    """
    units, tasks, bundles, traces = inputs
    task_ids = sorted(bundles["C5"].keys())
    base_rows, cand_rows = [], []
    for t in task_ids:
        base_rows.append(assemble(t, "A6-composed", 512, inputs))
        cand_rows.append(_assemble_v2(t, 512, inputs))
    base, cand = _mean(base_rows), _mean(cand_rows)
    breaches = []
    for metric in ("harmful_admission",):
        if (cand[metric] or 0) > (base[metric] or 0) + 1e-9:
            breaches.append(f"{metric}: {base[metric]} -> {cand[metric]}")
    for metric in ("contradiction_preservation",
                   "licence_preservation", "required_recall"):
        b, c = base[metric], cand[metric]
        if b is not None and c is not None and c < b - 1e-9:
            breaches.append(f"{metric}: {b} -> {c}")
    gain = round((cand["counted_tokens"] or 0)
                 - (base["counted_tokens"] or 0), 1)
    return {"candidate": "v2-drop-refutes-first",
            "rationale": "treat contradiction as ordinary budget "
                         "weight (repair for a crowding dissent)",
            "base_required_recall": base["required_recall"],
            "candidate_required_recall": cand["required_recall"],
            "base_tokens": base["counted_tokens"],
            "candidate_tokens": cand["counted_tokens"],
            "token_delta": gain,
            "breaches": breaches,
            "promoted": not breaches and gain < 0}


def _assemble_v2(task_id: str, budget, inputs) -> dict:
    """v2-drop-refutes-first variant: contradiction unprotected."""
    units, tasks, bundles, traces = inputs
    prefs, query, objective, as_of, ledger, project = _prefs(
        task_id, traces)
    trace = AssemblyTrace(task_id=task_id,
                          condition="A6-v2-drop-refutes-first",
                          budget=budget)
    c5 = bundles["C5"][task_id]
    rows = A._working_set(c5, units, traces.get(task_id), prefs)
    rows = op_order(rows, trace, "evidence-first")
    rows = op_dedup(rows, trace)
    rows = op_group(rows, trace)
    rows = op_mark(rows, trace, as_of)
    rows = op_drop(rows, trace, budget, len(prefs),
                   drop_refutes_first=True)
    text = render(rows, query, objective, as_of)
    return _finish(task_id, "A6-v2-drop-refutes-first", budget, rows,
                   text, trace, 0.0, units, tasks[task_id], ledger,
                   project, as_of, c5)
