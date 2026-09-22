"""Chapter 12 suite driver: frozen contexts in, paired comparisons out.

Condition ladder per task (§41), applicability recorded, never
assumed. Ablation bases prefer A6@768 and fall back to C5-full when
the decisive unit is absent from the tighter budget; the base used is
recorded per task.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import contexts as C
from . import metrics as M
from . import prompts as P
from . import runner as R
from .model import BehaviorTask
from .runner import ReaderClient
from .tasks import all_tasks, task_by_id

DERIVED_TEXTS = {
    "c-docs-flags": (
        "[derived-loop c-docs-flags | sources: snap-docs-0207, adr-013]\n"
        "Current state (snap-docs-0207, 2025-02-06): docs page lists "
        "corpus_import flags. Expected state (adr-013, 2025-01-13): "
        "legacy corpus_import domain removed. Difference: docs still "
        "describe removed flags."),
    "c-cli-half": (
        "[derived-loop c-cli-half | sources: snap-cli-0207, issue-088]\n"
        "Current state (snap-cli-0207, 2025-02-06): 4 of 9 CLI call "
        "sites still import corpus_import. Expected state (issue-088, "
        "2025-01-14): migrate CLI callers away. Difference: remaining "
        "CLI callers unmigrated."),
    "c-web": (
        "[derived-loop c-web | sources: snap-web-0207, issue-089]\n"
        "Current state (snap-web-0207, 2025-02-06): web call sites still "
        "import corpus_import. Expected state (issue-089, 2025-01-14): "
        "migrate web callers away. Difference: web callers unmigrated."),
    # Bare unconstrained listing: what an unguarded derived loop looks
    # like. No contract warning is embedded — the warning is what the
    # staged gate adds, and BW tests the listing without it.
    "c-facade-listing": (
        "[unfiltered listing c-facade-delete | sources: snap-facade-0207, "
        "adr-013]\nApparent consequence: delete the compatibility facade "
        "now that the domain is removed. Recommended action: "
        "DELETE_FACADE."),
}

# task_id -> {ch10 task supplying frozen bundles, conditions, wrong units}.
PLAN = {
    "fix-store": {"ch10": "T4-current-vs-stale",
                  "conds": ("B0", "B1", "B1P", "B2", "B3", "B4", "BO",
                            "BA", "BR", "BW", "BS"),
                  "wrong": ("mb-stale-sqlite",)},
    "ship-ch10": {"ch10": "T7-release",
                  "conds": ("B0", "B1", "B1P", "B2", "B3", "B4", "BO",
                            "BA", "BR", "BW"),
                  "wrong": ("mb-stale-ch10-plan", "mb-stale-ch06-title")},
    "release-blockers": {"ch10": "T7-release",
                         "conds": ("B0", "B1", "B1P", "B2", "B3", "B4", "BO",
                                   "BA", "BR"),
                         "wrong": ()},
    "credit-rule": {"ch10": "T1-architecture",
                    "conds": ("B0", "B1", "B1P", "B2", "B3", "B4", "BO",
                              "BA", "BR", "BW"),
                    "wrong": ("mb-stale-ch10-plan",)},
    "cite-rule": {"ch10": "T5-support-vs-topicality",
                  "conds": ("B0", "B1", "B1P", "B2", "B3", "B4", "BO",
                            "BA", "BR", "BW", "BS"),
                  "wrong": ("wr-evidence-policy", "cc-evidence-refs")},
    "review-prose": {"ch10": "T1-publication",
                     "conds": ("B0", "B1", "B1P", "B2", "B3", "B4", "BO"),
                     "wrong": ()},
    "review-arch": {"ch10": "T1-architecture",
                    "conds": ("B0", "B1", "B1P", "B2", "B3", "B4", "BO",
                              "BA", "BR"),
                    "wrong": ()},
    "corpus-cleanup": {"ch10": None,
                       "conds": ("B0", "B1", "B4", "BA", "BR", "BW"),
                       "wrong": ()},
    "irrelevant": {"ch10": "T1-publication",
                   "conds": ("B0", "B2", "B3"),
                   "wrong": ()},
}

REPEAT_TASKS = ("fix-store", "ship-ch10", "corpus-cleanup")
REPEAT_CONDS = ("B0", "B4")
REPEATS = 3


def cleanup_entry(condition: str) -> dict:
    """Custom contexts for the derived world (no ch10 bundles exist)."""
    staged = "\n\n---\n\n".join(
        DERIVED_TEXTS[k] for k in ("c-docs-flags", "c-cli-half", "c-web"))
    full = "\n\n---\n\n".join(
        DERIVED_TEXTS[k] for k in
        ("c-docs-flags", "c-cli-half", "c-web", "c-facade-listing"))
    if condition == "B0":
        entry = {"context": "", "memory_ids": [],
                 "note": "no memory"}
    elif condition == "B1":
        entry = {"context": full, "memory_ids": sorted(DERIVED_TEXTS),
                 "note": "full candidate listing (unfiltered world)"}
    elif condition == "B4":
        entry = {"context": staged,
                 "memory_ids": ["c-docs-flags", "c-cli-half", "c-web"],
                 "note": "staged-gate admitted triples (Ch11 output)"}
    elif condition == "BA":
        entry = {"context": DERIVED_TEXTS["c-docs-flags"],
                 "memory_ids": ["c-docs-flags"],
                 "note": "staged minus decisive caller loops"}
    elif condition == "BR":
        entry = {"context": staged,
                 "memory_ids": ["c-docs-flags", "c-cli-half", "c-web"],
                 "note": "BA plus restored caller loops"}
    elif condition == "BW":
        entry = {"context": DERIVED_TEXTS["c-facade-listing"],
                 "memory_ids": ["c-facade-listing"],
                 "note": "facade-deletion listing (harmful positive control)"}
    else:
        raise ValueError(condition)
    return C.finalize(entry)


def ablation_base(task: BehaviorTask, plan: dict,
                  texts: dict) -> tuple[str, dict]:
    """Prefer A6@768; fall back to C5-full when decisive units are
    absent from the tighter budget. Returns (base_condition, entry)."""
    if task.task_id == "corpus-cleanup":
        return "B4", cleanup_entry("B4")
    for condition in ("B4", "B3"):
        entry = C.finalize(C.build_condition(
            plan["ch10"], condition, texts, task.decisive_units, (),
            ch10_task=plan["ch10"]))
        members = _render_members(task, entry, texts, plan)
        if all(d in members for d in task.decisive_units):
            return condition, entry
    entry = C.finalize(C.build_condition(
        plan["ch10"], "B3", texts, task.decisive_units, (),
        ch10_task=plan["ch10"]))
    return "B3", entry


def _render_members(task: BehaviorTask, entry: dict, texts: dict,
                    plan: dict) -> set[str]:
    found = set()
    context = entry["context"]
    for uid in list(texts) + list(task.decisive_units):
        if f"item {uid}" in context or uid in context:
            found.add(uid)
    return found


def membership_for(ch10_task: str | None, texts: dict) -> dict:
    """Frozen membership sets for B0-B3 attribution."""
    if ch10_task is None:
        return {"corpus": set(), "c0": set(), "c5": set(), "a6": set(),
                "here": set()}
    c0 = set(C._members(C.load_bundle(ch10_task, "C0")))
    c5 = set(C._members(C.load_bundle(ch10_task, "C5")))
    a6_path = (C.CH14_RUN / "assembly-traces" / "A6-composed-budget-768.json")
    a6_all = json.loads(a6_path.read_text()).get(ch10_task, {})
    a6 = {i["unit_id"] for i in a6_all.get("items", ())
          if i.get("state") == "kept"}
    a6 |= {u for i in a6_all.get("items", ())
           for u in i.get("represents", ())}
    return {"corpus": set(texts), "c0": c0, "c5": c5, "a6": a6,
            "here": set()}


def run_suite(client: ReaderClient, tasks: list[BehaviorTask] | None = None,
              repeats: bool = True,
              resume: dict | None = None,
              conditions: set[str] | None = None) -> dict:
    """Run the suite, resuming cached (task, condition, repeat) rows.

    `resume` maps condition -> [{outcome, context, note}] from an
    earlier partial run. A stored row is reused only when the rebuilt
    entry hashes to the same context (code changes invalidate).
    `conditions` optionally restricts the pass-2 ladder (B0 always
    runs: it seeds attribution and deltas); ``None`` runs everything.
    Transfer drivers use this for staged passes (core ladder first,
    interventions second) without duplicating the runner.
    """
    texts = C.corpus_texts()
    tasks = tasks if tasks is not None else all_tasks()
    suite: dict = {"conditions": {}, "membership": {},
                   "ablation_base": {}}
    resumed = _index_resume(resume or {})
    # Pass 1: B0 everywhere (needed for B4 attribution + deltas).
    b0_types: dict[str, list[str]] = {}
    for task in tasks:
        plan = PLAN[task.task_id]
        entry = (cleanup_entry("B0") if task.task_id == "corpus-cleanup"
                 else C.finalize(C.build_condition(
                     plan["ch10"], "B0", texts, task.decisive_units, (),
                     ch10_task=plan["ch10"])))
        outcome = _maybe_resumed(
            suite, task, "B0", entry, client, 0,
            membership_for(plan["ch10"], texts), None, resumed)
        _store(suite, outcome, entry)
        b0_types[task.task_id] = [a.get("action_type")
                                  for a in outcome.structured_actions]
    # Pass 2: remaining conditions.
    for task in tasks:
        plan = PLAN[task.task_id]
        membership = membership_for(plan["ch10"], texts)
        base_cond, base_entry = (
            (None, None) if task.task_id in ("corpus-cleanup",)
            or not task.decisive_units
            else ablation_base(task, plan, texts))
        if base_cond is not None:
            suite["ablation_base"][task.task_id] = base_cond
        for condition in plan["conds"]:
            if condition == "B0":
                continue
            if conditions is not None and condition not in conditions:
                continue
            n_repeats = (REPEATS if repeats and task.task_id
                         in REPEAT_TASKS and condition in REPEAT_CONDS
                         else 1)
            for rep in range(n_repeats):
                if task.task_id == "corpus-cleanup":
                    entry = cleanup_entry(condition)
                elif condition in ("BA", "BR") and base_cond is not None:
                    entry = _ablation_entry(task, plan, texts, base_cond,
                                            base_entry, condition)
                else:
                    entry = C.finalize(C.build_condition(
                        plan["ch10"], condition, texts,
                        task.decisive_units, plan["wrong"],
                        ch10_task=plan["ch10"]))
                here = _here_units(task, entry, texts, plan)
                membership_here = dict(membership, here=here)
                outcome = _maybe_resumed(
                    suite, task, condition, entry, client, rep,
                    membership_here, b0_types[task.task_id], resumed)
                _store(suite, outcome, entry)
    return suite


def _ablation_entry(task, plan, texts, base_cond, base_entry,
                    condition):
    if condition == "BA":
        context = C.strip_units(base_entry["context"],
                                set(task.decisive_units))
        entry = {"context": context, "memory_ids": ["ablated"],
                 "note": f"{base_cond} minus decisive"}
    else:
        stripped = C.strip_units(base_entry["context"],
                                 set(task.decisive_units))
        present = ("A6-composed", "768") if base_cond == "B4" else None
        if task.task_id == "corpus-cleanup":
            return cleanup_entry("BR")
        context = C.append_units(stripped, list(task.decisive_units),
                                 texts, "restored decisive evidence")
        entry = {"context": context, "memory_ids": ["ablated+restored"],
                 "note": f"{base_cond} minus-plus decisive"}
    return C.finalize(entry)


def _here_units(task, entry, texts, plan) -> set[str]:
    return _render_members(task, entry, texts, plan)


def _index_resume(resume: dict) -> dict:
    index = {}
    for cond, rows in resume.items():
        for row in rows:
            outcome = row["outcome"]
            index[(outcome["task_id"], cond,
                   outcome.get("repeat_index", 0))] = row
    return index


def _maybe_resumed(suite: dict, task, condition: str, entry: dict,
                   client, repeat: int, membership, no_memory_types,
                   resumed: dict):
    """Reuse a stored outcome row when the rebuilt context hashes
    identically; otherwise run the condition live."""
    key = (task.task_id, condition, repeat)
    stored = resumed.get(key)
    if (stored is not None
            and stored["outcome"].get("context_hash")
            == entry["context_hash"]):
        from .model import BehaviorOutcome
        raw = stored["outcome"]
        return BehaviorOutcome(
            task_id=raw["task_id"],
            memory_condition=raw["memory_condition"],
            context_hash=raw["context_hash"],
            context_tokens=raw["context_tokens"],
            memory_ids=tuple(raw["memory_ids"]),
            structured_actions=tuple(raw["structured_actions"]),
            answer_text="", parse_ok=raw["parse_ok"],
            dimension_scores=tuple(raw["dimension_scores"].items()),
            task_score=raw["task_score"],
            failure_classes=tuple(raw["failure_classes"]),
            repeat_index=raw.get("repeat_index", 0),
            reader=raw.get("reader", ""))
    return R.run_condition(
        task, condition, entry, client.ask, client.name,
        repeat=repeat, membership=membership,
        no_memory_types=no_memory_types)


def _store(suite: dict, outcome, entry: dict) -> None:
    slot = suite["conditions"].setdefault(outcome.memory_condition, [])
    slot.append({"outcome": outcome.to_dict(),
                 "context": entry.get("context", ""),
                 "note": entry.get("note", "")})


def _task_averaged(task_ids: list[str], by_task_cond: dict,
                   cond: str) -> list:
    """One value per task: repeats averaged within task first."""
    from . import metrics as M
    vals = []
    for tid in task_ids:
        outs = [_pseudo(o) for o in by_task_cond.get((tid, cond), [])]
        scores = [o.task_score for o in outs if o.task_score is not None]
        if scores:
            vals.append(sum(scores) / len(scores))
    return vals


def summarize(suite: dict) -> dict:
    """Per-condition means, matched-set means, paired deltas,
    influence tables (strict four-cell + directional)."""
    from . import metrics as M
    by_task_cond: dict = {}
    for cond, rows in suite["conditions"].items():
        for row in rows:
            o = row["outcome"]
            by_task_cond.setdefault(
                (o["task_id"], cond), []).append(o)
    conditions = sorted(suite["conditions"])
    mean: dict = {}
    for cond in conditions:
        outs = [r["outcome"] for r in suite["conditions"][cond]]
        pseudo = [_pseudo(o) for o in outs]
        mean[cond] = {
            "n": len(outs),
            "dimensions": M.dimension_means(pseudo),
            "task_success": M.task_success_rate(pseudo),
            "harmful": M.harmful_rate(pseudo),
            "mean_tokens": round(sum(o["context_tokens"] for o in outs)
                                 / len(outs), 1) if outs else None,
        }
    # Matched task set: tasks running every condition in the ladder
    # core (B0/B2/B3/B4/BO), so cross-condition means compare the
    # same tasks. Repeats averaged within task first.
    core = ("B0", "B2", "B3", "B4", "BO")
    matched = sorted(
        t for t in {tid for (tid, _) in by_task_cond}
        if all((t, c) in by_task_cond for c in core))
    matched_means = {}
    for cond in conditions:
        vals = _task_averaged(matched, by_task_cond, cond)
        toks = [o["context_tokens"]
                for tid in matched
                for o in by_task_cond.get((tid, cond), [])]
        matched_means[cond] = {
            "tasks": matched,
            "n_tasks": len(vals),
            "task_success_macro": (round(sum(vals) / len(vals), 4)
                                   if vals else None),
            "mean_tokens": (round(sum(toks) / len(toks), 1)
                            if toks else None),
        }
    pairs = []
    for (tid, cond), outs in by_task_cond.items():
        if cond == "B0":
            continue
        base = by_task_cond.get((tid, "B0"), [None])[0]
        if base is None:
            continue
        for treated in outs:
            pairs.append((_pseudo(base), _pseudo(treated)))
    influence = M.influence_table(pairs)
    directional = M.directional_table(pairs)
    deltas = {}
    for (tid, cond), outs in by_task_cond.items():
        if cond == "B0":
            continue
        base = by_task_cond.get((tid, "B0"), [None])[0]
        if base is None:
            continue
        ds = [M.paired_delta(_pseudo(base), _pseudo(t))["task_delta"]
              for t in outs]
        ds = [d for d in ds if d is not None]
        deltas[f"{tid}|{cond}"] = {
            "task_delta": ds[0] if ds else None,
            "repeats": len(ds)}
    return {"mean_by_condition": mean, "matched_means": matched_means,
            "influence": influence, "directional": directional,
            "deltas": deltas}


def _pseudo(outcome_dict: dict):
    from .model import BehaviorOutcome
    return BehaviorOutcome(
        task_id=outcome_dict["task_id"],
        memory_condition=outcome_dict["memory_condition"],
        context_hash=outcome_dict["context_hash"],
        context_tokens=outcome_dict["context_tokens"],
        memory_ids=tuple(outcome_dict["memory_ids"]),
        structured_actions=tuple(outcome_dict["structured_actions"]),
        answer_text="", parse_ok=outcome_dict["parse_ok"],
        dimension_scores=tuple(outcome_dict["dimension_scores"].items()),
        task_score=outcome_dict["task_score"],
        failure_classes=tuple(outcome_dict["failure_classes"]),
        repeat_index=outcome_dict["repeat_index"],
        reader=outcome_dict["reader"])
