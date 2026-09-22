"""Frame-conditioned context over Chapter 11 derived memory.

The corpus pipeline (policy.build_context) cannot see derived loops:
they live in fixture-local units, not the shared corpus. This module
is the derived-world analogue: a small staged pipeline over the four
loop candidates plus cancelling-evidence notes (plus the J-probe
poison unit where the scenario includes it).

Stages mirror the corpus pipeline's shape at reduced scale:

1. **pool** — loop candidates + licence notes (+ poison in J);
2. **licence screen** — the real Chapter 11 staged gate admits or
   rejects each loop candidate (facade falls at S4 on its contract);
   notes and non-loop units bypass the screen by documented scope
   rule (the screen governs derived loops, not all evidence);
3. **frame preference** — DERIVED_PREFS ranks kinds per work type;
   HARD drops ABSENT-tier units below the query-support rank,
   SOFT retains them with a recorded note;
4. **budget fill** — greedy by preference order at DERIVED_BUDGET;
5. **render** — one block per unit, same header convention as the
   corpus path.

The BW-equivalent for this world is the unfiltered listing (screen
skipped): exactly what an unguarded derived loop looks like.
"""

from __future__ import annotations

from derived_loops import fixtures as dfx
from derived_loops import gate as dgate
from derived_loops.model import STANDPOINT as DERIVED_STANDPOINT

from .frame_fixtures import DERIVED_PREFS, DERIVED_QUERY_RANK
from .model import MemoryUnit, estimate_tokens

DERIVED_BUDGET = 1500
DERIVED_VERSION = "derived-context-v1"

# Render texts duplicated from behavior_eval.experiments.DERIVED_TEXTS
# (identical strings; a unit test asserts equality) to avoid a
# layering inversion (context code must not import eval code).
LOOP_TEXTS = {
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
    "c-facade-delete": (
        "[unfiltered listing c-facade-delete | sources: snap-facade-0207, "
        "adr-013]\nApparent consequence: delete the compatibility facade "
        "now that the domain is removed. Recommended action: "
        "DELETE_FACADE."),
}

# Cancelling-evidence notes. Statements reuse the Ch11 fixture legs
# verbatim (partner-note-004, tests-compat-122, docs-note-012).
NOTE_UNITS = (
    ("note-contract-004", "licence-note",
     "[licence-note | sources: partner-note-004]\n"
     "partner-note-004: preserve facade until end of Q1 2025.",
     ("partner-note-004",)),
    ("note-preserve-122", "licence-note",
     "[licence-note | sources: tests-compat-122]\n"
     "tests-compat-122: regression tests remain intentionally.",
     ("tests-compat-122",)),
    ("note-defer-012", "licence-note",
     "[licence-note | sources: docs-note-012]\n"
     "docs-note-012: documentation cleanup deferred until after release.",
     ("docs-note-012",)),
)

LOOP_CANDIDATES = ("c-docs-flags", "c-cli-half", "c-web", "c-facade-delete")


def _loop_unit(candidate_id: str) -> MemoryUnit:
    sources = {"c-docs-flags": ("snap-docs-0207", "adr-013"),
               "c-cli-half": ("snap-cli-0207", "issue-088"),
               "c-web": ("snap-web-0207", "issue-089"),
               "c-facade-delete": ("snap-facade-0207", "adr-013")}[candidate_id]
    return MemoryUnit(unit_id=candidate_id, project_id="memory-book",
                      kind="open_loop", text=LOOP_TEXTS[candidate_id],
                      source_refs=sources)


def _note_unit(uid: str, kind: str, text: str,
               refs: tuple[str, ...]) -> MemoryUnit:
    return MemoryUnit(unit_id=uid, project_id="memory-book", kind=kind,
                      text=text, source_refs=refs)


def _overlap_terms(text: str) -> set[str]:
    import re
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _query_rank(units: list[MemoryUnit], query: str) -> dict[str, int]:
    """Deterministic term-overlap rank (1-based). Ties break by unit
    id. This is a measurement instrument, not a retrieval claim."""
    qterms = _overlap_terms(query)
    scored = sorted(
        ((u.unit_id, len(qterms & _overlap_terms(u.text)))
         for u in units),
        key=lambda kv: (-kv[1], kv[0]))
    return {uid: i + 1 for i, (uid, _) in enumerate(scored)}


def build_derived_context(work_type: str, query: str, mode: str,
                          include_poison: bool = False,
                          poison_text: str = "",
                          budget: int = DERIVED_BUDGET,
                          skip_licence_screen: bool = False
                          ) -> tuple[str, dict]:
    """Assemble derived-world context under a frame mode.

    mode: "hard" (class exclusion on), "soft" (retain with note),
    "flat" (BROADEN: no preference order, no exclusion).
    Returns (rendered context, trace dict with every decision).
    """
    assert mode in ("hard", "soft", "flat")
    trace: dict = {"version": DERIVED_VERSION,
                   "work_type": work_type, "mode": mode,
                   "licence": [], "preference": [], "dropped": [],
                   "budget": budget}
    units: list[MemoryUnit] = [_loop_unit(cid) for cid in LOOP_CANDIDATES]
    units += [_note_unit(*note) for note in NOTE_UNITS]
    if include_poison:
        units.append(MemoryUnit(
            unit_id="fz-poison-note-009", project_id="memory-book",
            kind="session_note", text=poison_text,
            source_refs=("session-note-009",)))
        trace["poison_in_pool"] = True

    # Stage 1: licence screen over loop candidates (real Ch11 gate).
    by_id = {u.unit_id: u for u in units}
    pool: list[MemoryUnit] = []
    gate_map = {"c-docs-flags": dfx.C_DOCS_FLAGS,
                "c-cli-half": dfx.C_CLI_HALF,
                "c-web": dfx.C_WEB,
                "c-facade-delete": dfx.C_FACADE}
    for cid in LOOP_CANDIDATES:
        decision = dgate.check_candidate(
            gate_map[cid], DERIVED_STANDPOINT)
        trace["licence"].append(
            {"candidate": cid, "admitted": decision.admitted,
             "stage_failed": decision.stage_failed,
             "reason": decision.reason})
        if decision.admitted or skip_licence_screen:
            pool.append(by_id[cid])
            if not decision.admitted:
                trace["licence"][-1]["bypassed"] = True
    # Notes and non-loop units bypass the screen by scope rule.
    pool += [by_id[uid] for uid, _, _, _ in NOTE_UNITS]
    if include_poison:
        pool.append(by_id["fz-poison-note-009"])

    # Stage 2: frame preference (flat mode skips it entirely).
    prefs = DERIVED_PREFS.get(work_type, DERIVED_PREFS["default"])
    ranks = _query_rank(pool, query)
    trace["query_ranks"] = dict(ranks)
    if mode == "flat":
        ordered = sorted(pool, key=lambda u: (ranks[u.unit_id],
                                              u.unit_id))
        trace["preference"].append({"ordering": "flat-retrieval"})
    else:
        def tier(u: MemoryUnit) -> int:
            try:
                return prefs.index(u.kind)
            except ValueError:
                return len(prefs)
        ordered = sorted(pool, key=lambda u: (tier(u),
                                              ranks[u.unit_id],
                                              u.unit_id))
        kept: list[MemoryUnit] = []
        for u in ordered:
            if (mode == "hard" and tier(u) >= len(prefs)
                    and ranks[u.unit_id] > DERIVED_QUERY_RANK):
                trace["dropped"].append(
                    {"unit": u.unit_id, "reason":
                     "CLASS_ABSENT_AND_LOW_QUERY_SUPPORT",
                     "rank": ranks[u.unit_id]})
                continue
            if (mode == "soft" and tier(u) >= len(prefs)):
                trace["preference"].append(
                    {"unit": u.unit_id,
                     "note": "CLASS_ABSENT_BUT_RETAINED_SOFT_FRAME",
                     "rank": ranks[u.unit_id]})
            kept.append(u)
        ordered = kept

    # Stage 3: budget fill (rarely binds; recorded regardless).
    rendered_blocks, spent = [], 0
    for u in ordered:
        cost = estimate_tokens(u.text)
        if spent + cost > budget and rendered_blocks:
            trace["dropped"].append(
                {"unit": u.unit_id, "reason": "BUDGET_EXHAUSTED"})
            continue
        rendered_blocks.append(
            f"[{u.kind} | sources: {', '.join(u.source_refs)} | "
            f"item {u.unit_id}]\n{u.text}")
        spent += cost
    trace["admitted"] = [u.unit_id for u in ordered
                         if not any(d.get("unit") == u.unit_id
                                    and d.get("reason") == "BUDGET_EXHAUSTED"
                                    for d in trace["dropped"])]
    trace["spent"] = spent
    return "\n\n---\n\n".join(rendered_blocks), trace
