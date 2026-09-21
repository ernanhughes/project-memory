"""C7 deterministic context assembly (next5 C7 pass).

Input: the C6-admitted candidate set. C7 never reinterprets
validity, scope, frame establishment, or trust: it selects,
deduplicates, groups, and budgets. Every inclusion/exclusion
carries a rule code; the trace records candidate set, decisions,
groups, ordering, tokens, and hash.

Assembly rules (fixed order of application for A6):

1. decisive: current-decision display ids for the task topic.
2. support: per-level rule (overlap-best / full chain / ledger-first).
3. redundancy: drop derived units whose entire root chain is
   present (echo collapse), unless the unit adds unique claim text
   absent from its roots. Roots identified via ledger derived
   edges; claim uniqueness by normalized content equality.
4. grouping: decisive first, then support by date, then remainder
   by display id. Order-only treatment.
5. budget: drop lowest-overlap units beyond BUDGET_CHARS (ties by
   display id), decisive units exempt.

Token budget rule (outcome-blind): half the median A0 size on the
frozen family, rounded (10586 -> 5000 chars). Chosen from
deterministic size inspection before any behavioral measurement;
no scores were consulted.

Reason codes: select.decisive, select.support-overlap,
select.support-ledger, select.support-chain, drop.redundant-echo,
drop.over-budget, keep.ungrounded (admitted but unselected by a
rule: visible in trace, never silently dropped).
"""

from __future__ import annotations

BUDGET_CHARS = 5000


def _chars(view: dict) -> int:
    return len(view.get("title") or "") + len(view.get("body") or "")


def select_decisive(admitted: list[dict], decisive_ids: set[str]):
    kept, trace = [], {}
    for view in admitted:
        if view["display_id"] in decisive_ids:
            kept.append(view)
            trace[view["display_id"]] = "select.decisive"
    return kept, trace


def overlap_score(query: str, view: dict) -> int:
    """Content-word overlap between a query and a view. Public so
    ranking-adjacent callers share one scalar with the ranking."""
    from generator.queries import content_words
    qw = set(content_words(query))
    vw = set(content_words(view.get("title", "")
                           + " " + view.get("body", "")))
    return len(qw & vw)



def select_support_overlap(admitted: list[dict], decisive_ids: set[str],
                           query: str):
    """Single highest-overlap supporting unit (minimal provenance).
    Ties break by smallest display id, matching ranking order."""
    cands = [v for v in admitted if v["display_id"] not in decisive_ids]
    if not cands:
        return [], {}
    ordered = sorted(cands,
                     key=lambda v: (-overlap_score(query, v),
                                    v["display_id"]))
    chosen = ordered[0]
    return [chosen], {chosen["display_id"]: "select.support-overlap"}


def select_support_chain(admitted: list[dict], support_ids: set[str]):
    """Full supporting chain (WO analog): every support id present."""
    kept, trace = [], {}
    for view in admitted:
        if view["display_id"] in support_ids:
            kept.append(view)
            trace[view["display_id"]] = "select.support-chain"
    return kept, trace


def select_support_ledger(admitted: list[dict], support_ids: list[str]):
    """Ledger-first support: earliest supported_by id present."""
    for did in support_ids:
        for view in admitted:
            if view["display_id"] == did:
                return [view], {did: "select.support-ledger"}
    return [], {}


def collapse_redundant(admitted: list[dict], derived_map: dict) -> tuple:
    """Drop derived units whose root chain is fully present, unless
    their normalized claim text is absent from their own present
    roots. derived_map: display_id -> (roots tuple, claim string).
    """
    present = {v["display_id"] for v in admitted}
    by_id = {v["display_id"]: v for v in admitted}
    kept, trace = [], {}
    for view in admitted:
        did = view["display_id"]
        if did not in derived_map:
            kept.append(view)
            continue
        roots, claim = derived_map[did]
        present_roots = [r for r in roots if r in present]
        if not set(roots) <= present:
            kept.append(view)
            trace[did] = "keep.ungrounded"
            continue
        known = {(by_id[r].get("body") or "").strip().lower()
                 for r in present_roots}
        if claim.strip().lower() in known:
            trace[did] = "drop.redundant-echo"
            continue
        kept.append(view)
        trace[did] = "keep.unique-claim"
    return kept, trace


def group_order(views: list[dict], decisive_ids: set[str],
                support_ids: set[str]) -> list[dict]:
    """Decisive first, then support by date, then remainder by id."""
    def key(view):
        did = view["display_id"]
        if did in decisive_ids:
            return (0, "", did)
        if did in support_ids:
            return (1, view.get("date", ""), did)
        return (2, "", did)
    return sorted(views, key=key)


def apply_budget(ordered: list[dict], decisive_ids: set[str],
                 budget: int = BUDGET_CHARS) -> tuple:
    """Keep decisive units always; keep non-decisive units in order
    while the running total stays within budget; drop the rest with
    drop.over-budget. Order otherwise preserved."""
    kept, trace = [], {}
    spent = 0
    for view in ordered:
        did = view["display_id"]
        cost = _chars(view)
        if did in decisive_ids or spent + cost <= budget:
            kept.append(view)
            spent += cost
        else:
            trace[did] = "drop.over-budget"
    return kept, trace
