"""Context assembly: what crosses the bottleneck, and in what form.

Chapter 10 selects (C5 is the frozen input; C6 is a comparison, never
the foundation, because its coalescing lowered precision 0.474 to
0.464). This module varies only what happens after admission:

  ORDER   same candidates and content, only ordering changes
  DEDUP   fold genuine echo/duplicate support (extractive only)
  GROUP   keep related evidence together (support chain, correction
          pair, Chapter 11 triple); never rewrite facts
  MARK    compact validity / provenance / derived-status marks in the
          reader-visible render
  DROP    explicit budget-driven dropping with a reason per drop

Runtime policy never sees hidden ledger labels (MUST/OPTIONAL/...).
It sees only: unit metadata (kind, validity, evidence role, echo
links, open-loop refs, source refs), Chapter 10 selection signals and
retrieval rank from the frozen C5 trace, and ProjectFrame/WorkFrame
preferences. Conditions that use the ledger are labelled `oracle`.

Token convention (Part XIV): `estimate_tokens` (chars//4) is preserved
as `counted` for comparability with Chapter 10. `rendered` counts the
full reader-visible render including source/validity headers. Both are
reported everywhere; neither is claimed to be exact model tokens.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .model import estimate_tokens

ASSEMBLY_VERSION = "assembly-v1"
DROP_POLICY_VERSION = "drop-preference-outside-first-v1"
RENDER_VERSION = "sectioned-evidence-v1"

# Budgets for the sweep (estimated tokens). "full" = C5 natural size.
BUDGETS: tuple = (384, 512, 768, 1024, 1280, 1536, "full")


# ---------------------------------------------------------------------------
# Frozen input loading.
# ---------------------------------------------------------------------------

def load_ch10_inputs(run_dir: str | None = None):
    """Load frozen C5/C6/CO bundles and C5 traces plus the corpus.

    Returns (units, tasks, bundles, traces) where bundles[condition]
    maps task_id -> bundle dict and traces maps task_id -> C5 trace.
    Paths anchor at the repository root, never at the CWD.
    """
    import json
    from pathlib import Path
    from .corpus import corpus
    from . import fixtures as fx

    root = Path(__file__).resolve().parent.parent.parent
    base = Path(run_dir) if run_dir else (
        root / "experiments" / "benchmark" / "runs"
        / "ch10-20260920T163314Z-context-frames")
    units = {u.unit_id: u for u in corpus()}
    tasks = {t.task_id: t for t in fx.all_tasks()}
    bundles: dict[str, dict] = {}
    for condition in ("C5", "C6", "CO"):
        table = {}
        for path in sorted((base / "bundles").glob(f"*-{condition}.json")):
            d = json.loads(path.read_text())
            task_id = path.name[: -len(f"-{condition}.json")]
            table[task_id] = d
        bundles[condition] = table
    traces = {}
    for path in sorted((base / "traces").glob("*-C5.json")):
        d = json.loads(path.read_text())
        traces[path.name[: -len("-C5.json")]] = d
    return units, tasks, bundles, traces


# ---------------------------------------------------------------------------
# Evidence-group ledger (hidden evaluation annotations).
# ---------------------------------------------------------------------------

def build_ledger(task, units) -> dict:
    """Hidden annotations over the C5-admitted set. Evaluation only.

    Groups:
      ALTERNATIVE_SUPPORT  echo/duplicate members of one claim group;
                           one representative suffices
      CONJUNCTIVE_SUPPORT  distinct MUST members sharing a claim group;
                           every one is necessary
      CORRECTION_PAIR      superseded unit + its successor
      CONFLICT_PAIR        refutes-role unit + the item it disputes
      DERIVED_LICENCE_GROUP open-loop unit + its licence legs
      INDEPENDENT_REQUIRED  MUST unit with no group cover
    """
    c5_ids = list(task.get("c5_members", ()))
    by_id = {u: units[u] for u in c5_ids if u in units}
    ledger_units = task.get("ledger", {})
    must = {u for u, lab in ledger_units.items() if lab == "MUST"}
    groups: dict[str, list[str]] = {}
    for uid, u in by_id.items():
        if u.claim_key:
            groups.setdefault(u.claim_key, []).append(uid)
    out = {"units": {}, "groups": {}}
    for uid, u in by_id.items():
        roles = []
        if u.evidence_role == "echo" or u.echo_of:
            roles.append("ALTERNATIVE_SUPPORT")
        if u.valid_until is not None and u.superseded_by:
            roles.append("CORRECTION_PAIR")
        if u.evidence_role == "refutes":
            roles.append("CONFLICT_PAIR")
        if u.open_loop:
            roles.append("DERIVED_LICENCE_GROUP")
        if uid in must and not u.claim_key:
            roles.append("INDEPENDENT_REQUIRED")
        out["units"][uid] = {
            "ledger_label": ledger_units.get(uid, "UNLABELLED"),
            "claim_key": u.claim_key,
            "roles": roles,
            "required": uid in must,
        }
    for key, members in groups.items():
        primaries = [m for m in members
                     if by_id[m].evidence_role != "echo"
                     and not by_id[m].echo_of]
        kind = ("ALTERNATIVE" if len(primaries) <= 1
                else "CONJUNCTIVE")
        out["groups"][key] = {"members": sorted(members),
                              "kind": kind}
    return out


# ---------------------------------------------------------------------------
# Assembly trace.
# ---------------------------------------------------------------------------

@dataclass
class AssemblyTrace:
    task_id: str
    condition: str
    budget: object
    operations: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0

    def log(self, operation: str, **detail) -> None:
        entry = {"operation": operation}
        entry.update(detail)
        self.operations.append(entry)

    def to_dict(self) -> dict:
        return {"task_id": self.task_id, "condition": self.condition,
                "budget": self.budget, "operations": self.operations,
                "items": self.items, "latency_ms": self.latency_ms,
                "assembly_version": ASSEMBLY_VERSION,
                "drop_policy_version": DROP_POLICY_VERSION,
                "render_version": RENDER_VERSION}


# ---------------------------------------------------------------------------
# Internal working set.
# ---------------------------------------------------------------------------

def _working_set(bundle: dict, units, trace: dict | None,
                 prefs: tuple[str, ...]) -> list[dict]:
    """One row per admitted member unit, in bundle order."""
    rank = {}
    signals = {}
    if trace is not None:
        for c in trace.get("candidates", ()):
            rank[c["candidate_id"]] = c.get("retrieval_rank", 10 ** 6)
            signals[c["candidate_id"]] = c.get("signals", {})
    rows = []
    order = []
    for item in bundle.get("items", ()):
        for uid in item.get("members", ()):
            order.append(uid)
    for pos, uid in enumerate(order):
        u = units.get(uid)
        if u is None:
            continue
        try:
            tier = prefs.index(u.kind)
        except ValueError:
            tier = len(prefs)
        rows.append({
            "unit_id": uid, "pos": pos, "unit": u,
            "text": u.text, "kind": u.kind,
            "tier": tier, "retrieval_rank": rank.get(uid, 10 ** 6),
            "signals": signals.get(uid, {}),
            "valid_until": u.valid_until,
            "superseded_by": u.superseded_by,
            "evidence_role": u.evidence_role,
            "echo_of": u.echo_of,
            "claim_key": u.claim_key,
            "open_loop": u.open_loop,
            "source_refs": list(u.source_refs),
            "project_id": u.project_id,
            "tokens": estimate_tokens(u.text),
            "state": "kept", "reason": "ADMITTED_BY_C5",
            "represented_by": None, "represents": [],
            "budget_before": None, "budget_after": None,
        })
    return rows


# ---------------------------------------------------------------------------
# Operations (each deterministic; each logged with real reasons).
# ---------------------------------------------------------------------------

def op_order(rows: list[dict], trace: AssemblyTrace,
             mode: str = "evidence-first") -> list[dict]:
    """Reorder only. Never adds or removes content."""
    if mode == "selection":
        out = sorted(rows, key=lambda r: r["pos"])
    elif mode == "evidence-first":
        out = sorted(rows, key=lambda r: (
            r["tier"], r["retrieval_rank"], r["pos"]))
    elif mode == "dependency":
        out = sorted(rows, key=lambda r: (
            r["claim_key"] or f"~{r['pos']:06d}",
            r["retrieval_rank"], r["pos"]))
    elif mode == "random":
        import random
        out = list(rows)
        random.Random(20260207).shuffle(out)
    else:
        raise ValueError(f"unknown order mode {mode!r}")
    trace.log("order", mode=mode,
              order=[r["unit_id"] for r in out])
    return out


def op_dedup(rows: list[dict], trace: AssemblyTrace) -> list[dict]:
    """Fold echo/duplicate support into a representative (extractive).

    Representative: first non-echo member of the claim group in current
    order, else the first member. Folded units keep their source refs
    on the representative and stay in the trace as folded, never deleted.
    Refutes-role units are never folded.
    """
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["claim_key"] or f"@@{r['unit_id']}", []).append(r)
    out = []
    for key, members in groups.items():
        foldable = [m for m in members
                    if (m["evidence_role"] == "echo" or m["echo_of"])
                    and m["evidence_role"] != "refutes"]
        if key.startswith("@@") or not foldable:
            out.extend(members)
            continue
        primaries = [m for m in members if m not in foldable]
        head = primaries[0] if primaries else members[0]
        for m in foldable:
            if m is head:
                continue
            m["state"] = "folded"
            m["reason"] = (f"ECHO_FOLDED_INTO {head['unit_id']} "
                           f"(claim group {key or 'n/a'})")
            m["represented_by"] = head["unit_id"]
            head["represents"].append(m["unit_id"])
            for ref in m["source_refs"]:
                if ref not in head["source_refs"]:
                    head["source_refs"].append(ref)
        trace.log("dedup", claim_key=key or None,
                  representative=head["unit_id"],
                  folded=[m["unit_id"] for m in foldable
                          if m is not head],
                  sources_preserved=list(head["source_refs"]))
        out.append(head)
        out.extend([m for m in primaries[1:]])
    # Preserve incoming relative order of surviving heads.
    pos = {id(r): i for i, r in enumerate(rows)}
    out.sort(key=lambda r: pos[id(r)])
    return out


def op_group(rows: list[dict], trace: AssemblyTrace) -> list[dict]:
    """Keep related evidence adjacent. No text is rewritten."""
    grouped = sorted(rows, key=lambda r: (
        r["claim_key"] or f"~{r['pos']:06d}", r["pos"]))
    by_key: dict[str, list[str]] = {}
    for r in grouped:
        if r["claim_key"]:
            by_key.setdefault(r["claim_key"], []).append(r["unit_id"])
    for r in grouped:
        if r["evidence_role"] == "refutes" and r["claim_key"]:
            others = [u for u in by_key[r["claim_key"]]
                      if u != r["unit_id"]]
            r["conflict_note"] = ", ".join(others) or "group"
    trace.log("group",
              groups=[{"claim_key": r["claim_key"] or None,
                       "unit_id": r["unit_id"]} for r in grouped])
    return grouped


def validity_mark(row: dict, as_of: str) -> str:
    """Compact reader-visible validity mark for one row."""
    if row["valid_until"] is not None:
        succ = row["superseded_by"] or "successor"
        return f"SUPERSEDED->{succ} (historical, not current as of {as_of})"
    return f"CURRENT as of {as_of}"


def op_mark(rows: list[dict], trace: AssemblyTrace,
            as_of: str) -> list[dict]:
    """Attach compact marks. Marks are data, not prose."""
    for r in rows:
        marks = [validity_mark(r, as_of)]
        if r["evidence_role"] == "refutes":
            marks.append("DISPUTES fellow-group claim (unresolved)")
        if r["open_loop"]:
            marks.append(f"DERIVED-LICENCE open-loop {r['open_loop']}")
        if r["represents"]:
            marks.append(
                f"also-supported-by {len(r['represents'])} folded restatement(s)")
        r["marks"] = marks
    trace.log("mark", marked=len(rows), as_of=as_of)
    return rows


def _droppable_tier(row: dict) -> int:
    """Runtime droppability from metadata only (no ledger labels).

    Lower tier drops first: superseded-only history, then kinds outside
    the frame preferences, then everything else by reverse order.
    Refutes units and open-loop units are never in the first two tiers.
    """
    if row["evidence_role"] == "refutes" or row["open_loop"]:
        return 3
    if row["valid_until"] is not None:
        return 0
    # tier == len(prefs) means "kind absent from frame preferences".
    if row.get("kind_absent", False):
        return 1
    return 2


def op_drop(rows: list[dict], trace: AssemblyTrace, budget,
            prefs_len: int, oracle_keep: set[str] | None = None,
            random_drop: bool = False,
            history_last: bool = False,
            protect_outside: bool = False,
            drop_refutes_first: bool = False) -> list[dict]:
    """Fit rows to budget. Every drop carries a reason and cover note.

    `history_last` (backtest variant): superseded history drops last
    instead of first. `protect_outside` (backtest variant): kinds
    outside the frame preferences are kept first — the deliberately
    wrong repair for a case where in-preference evidence was dropped.
    `drop_refutes_first` (backtest variant): contradiction is treated
    as ordinary budget weight — the wrong repair for a case where a
    long dissent crowded out supporting evidence.
    """
    if budget == "full":
        for r in rows:
            r["budget_before"] = r["budget_after"] = "full"
        trace.log("drop", policy="none", budget=budget)
        return rows
    if random_drop:
        import random
        order = list(rows)
        random.Random(99).shuffle(order)
        keep, drop = [], []
        spent = 0
        for r in order:
            if spent + r["tokens"] <= budget:
                keep.append(r)
                spent += r["tokens"]
            else:
                drop.append(r)
        for r in drop:
            r["state"] = "dropped"
            r["reason"] = "RANDOM_DROP (control)"
        trace.log("drop", policy="random-control", budget=budget,
                  kept=[r["unit_id"] for r in keep],
                  dropped=[r["unit_id"] for r in drop])
        keep.sort(key=lambda r: r["pos"])
        return keep
    for r in rows:
        r["kind_absent"] = (r["tier"] >= prefs_len)
    if oracle_keep is not None:
        # Oracle fitting: hidden-label order MUST, SHOULD, OPTIONAL, other.
        # This branch is labelled `oracle` everywhere it is used.
        def okey(r):
            lab = oracle_keep.get(r["unit_id"], "OTHER")
            return ({"MUST": 0, "SHOULD": 1, "OPTIONAL": 2}.get(lab, 3),
                    r["pos"])
        ordered = sorted(rows, key=okey)
        policy = "oracle-ledger-order"
    else:
        def tier_of(r):
            t = _droppable_tier(r)
            if history_last and t == 0:
                return 4
            return t
        # Keep order: contradiction and open loops first (tier 3),
        # then ordinary evidence (2), then preference-outside kinds
        # (1), then superseded history (0). Dropping starts at the end.
        # protect_outside inverts tier 1/2: the wrong repair, kept for
        # the backtest.
        keep_rank = {3: 0, 2: 1, 1: 2, 0: 3, 4: 4}
        policy = DROP_POLICY_VERSION + (
            "-history-last" if history_last else "")
        if protect_outside:
            keep_rank = {3: 0, 1: 1, 2: 2, 0: 3, 4: 4}
            policy = DROP_POLICY_VERSION + "-protect-outside"
        if drop_refutes_first:
            # Contradiction treated as budget weight: refutes units
            # sort with ordinary evidence instead of protected first.
            # Open loops stay protected; only refutes move.
            _base_tier = tier_of

            def tier_of(r):  # noqa: F811
                if r["evidence_role"] == "refutes":
                    return 2
                return _base_tier(r)
            policy = DROP_POLICY_VERSION + "-drop-refutes-first"
        ordered = sorted(rows, key=lambda r: (
            keep_rank[tier_of(r)], r["pos"]))
    kept, spent = [], 0
    dropped_ids: list[str] = []
    for r in ordered:
        r["budget_before"] = budget - spent
        if spent + r["tokens"] <= budget or not kept:
            # Never emit an empty context while candidates exist: the
            # first item is kept even if it alone exceeds the budget,
            # and the overrun is recorded rather than hidden.
            kept.append(r)
            spent += r["tokens"]
            r["budget_after"] = budget - spent
        else:
            r["state"] = "dropped"
            dropped_ids.append(r["unit_id"])
            cover = None
            for k in kept:
                if (k["claim_key"] and k["claim_key"] == r["claim_key"]
                        and k["unit_id"] != r["unit_id"]):
                    cover = k["unit_id"]
                    break
            r["reason"] = (
                f"DROP_{'ORACLE' if oracle_keep is not None else 'BUDGET'} "
                f"tier={_droppable_tier(r)} saving={r['tokens']} "
                f"covered_by={cover or 'none'}")
            r["budget_after"] = budget - spent
            trace.log("drop-one", unit_id=r["unit_id"],
                      reason=r["reason"], tier=_droppable_tier(r))
    trace.log("drop", policy=policy, budget=budget,
              kept=[r["unit_id"] for r in kept],
              dropped=dropped_ids,
              spent=spent)
    kept.sort(key=lambda r: rows.index(r))
    return kept


# ---------------------------------------------------------------------------
# Rendering: subordinate evidence with structure, never instructions.
# ---------------------------------------------------------------------------

def render(rows: list[dict], task_query: str, work_objective: str,
           as_of: str, structured: bool = True) -> str:
    """Render the working context.

    Retrieved memory is always subordinate evidence under explicit
    section headers. Memory text is never merged into the task
    instruction block, so instruction-shaped memory cannot become a
    trusted instruction (F14-I).
    """
    head_lines = ["CURRENT WORK", task_query.strip(),
                  f"Objective: {work_objective.strip()}",
                  f"Standpoint: {as_of}"]
    head = "\n".join(head_lines)
    body_parts = []
    current = [r for r in rows if r["valid_until"] is None]
    historical = [r for r in rows if r["valid_until"] is not None]
    for section, members in (("MEMORY EVIDENCE", current),
                             ("HISTORICAL BACKGROUND", historical)):
        if not members and structured:
            continue
        if structured:
            body_parts.append(f"## {section}")
        for r in members:
            refs = ", ".join(r["source_refs"]) or "unsourced"
            header = (f"[{r['kind']} | sources: {refs} | "
                      f"item {r['unit_id']}]")
            marks = r.get("marks")
            if marks:
                header += "\n[" + "; ".join(marks) + "]"
            if r.get("conflict_note"):
                header += f"\n[disagrees with: {r['conflict_note']}]"
            body_parts.append(f"{header}\n{r['text']}")
    if not structured:
        flat = [head]
        for r in rows:
            refs = ", ".join(r["source_refs"]) or "unsourced"
            flat.append(f"[{r['kind']} | sources: {refs}]\n{r['text']}")
        return "\n\n---\n\n".join(flat)
    return head + "\n\n---\n\n" + "\n\n---\n\n".join(body_parts)


def count_rendered(text: str) -> int:
    return estimate_tokens(text)
