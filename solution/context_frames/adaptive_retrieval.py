"""Transparent adaptive-retrieval baseline (F7).

Not a reproduction of Self-RAG/CRAG/Adaptive-RAG: a small deterministic
rule over query-only retrieval statistics, with paper lineage
documented as inspiration. It decides narrow / broad / skip retrieval
from the raw fused ranking, using NO ProjectFrame validity signals —
that exclusion is the point. If frame establishment adds behavioural
value beyond this baseline, the gate has earned its keep; if not,
§93 Type F collapses the mechanism.

Signals (all retrieval-side, observable without any frame):
  top_score   raw fused score of rank 1 (agreement across lexical and
              dense paths raises it; single-path hits lower it)
  margin      (s0 - s1) / s0: how decisively one unit leads
  spread      distinct project ids among the top 10 hits
Branches:
  SKIP    top score below ABS_FLOOR: retrieve nothing (empty bundle).
  NARROW  high margin and single-project top-10: budget fill restricted
          to units scoring at least REL_FLOOR.
  BROAD   otherwise: greedy budget fill by score over the pool.

Thresholds are tuned on DEV fixtures only (see TUNING_SOURCES); the
eval run reuses them frozen. The tuning report lives in the run
manifest.
"""

from __future__ import annotations

ADAPTIVE_VERSION = "adaptive-retrieval-baseline-v1"

# Frozen provenance: these scenario IDs (and only these) informed the
# thresholds below. A test asserts this set is disjoint from the eval
# split. Values were chosen on dev retrieval statistics + dev
# behaviour, then frozen before any eval outcome existed.
TUNING_SOURCES = (
    "A-fix-dec-dev",
    "A-ship-dec-dev",
    "B-prose-weak-dev",
    "C-ship-shift-dev",
    "D-cleanup-conflict-dev",
    "E-cite-unknown-dev",
    "F-arch-queryonly-dev",
    "G-cite-noproject-dev",
    "K-cleanup-unknown-dev",
    "J-cleanup-poison-dev",
    "L-irrel-dec-dev",
)

# Provisional operating point (pre-dev). Final values are set from dev
# evidence and recorded in the manifest; the constants below are the
# starting point, not a result.
M_HI = 0.20
ABS_FLOOR = 0.008
REL_FLOOR = 0.016

SKIP = "SKIP_RETRIEVAL"
NARROW = "NARROW_TOP"
BROAD = "BROAD_FILL"


def adaptive_decide(ranked: list[tuple[str, float]],
                    units: dict,
                    budget: int,
                    m_hi: float = M_HI,
                    abs_floor: float = ABS_FLOOR,
                    rel_floor: float = REL_FLOOR) -> tuple[str, list[str],
                                                          dict]:
    """Decide retrieval breadth from the raw fused ranking.

    `ranked` is [(unit_id, raw_score)] descending from a query-only
    retrieve call; `units` maps id -> MemoryUnit (needs project_id and
    tokens). Returns (decision, kept unit ids, detail dict with the
    actual numbers behind the decision).
    """
    present = [(uid, s) for uid, s in ranked if uid in units]
    detail: dict = {"pool": len(present)}
    if not present:
        detail.update(top_score=0.0, margin=0.0, spread=0)
        return SKIP, [], detail
    top = present[:10]
    s0 = present[0][1]
    s1 = present[1][1] if len(present) > 1 else 0.0
    margin = round((s0 - s1) / s0, 4) if s0 > 0 else 0.0
    spread = len({units[uid].project_id for uid, _ in top})
    detail.update(top_score=round(s0, 5), margin=margin, spread=spread,
                  m_hi=m_hi, abs_floor=abs_floor, rel_floor=rel_floor)
    if s0 < abs_floor:
        detail["reason"] = "TOP_BELOW_FLOOR"
        return SKIP, [], detail
    if margin >= m_hi and spread == 1:
        kept, spent = [], 0
        for uid, score in present:
            if score < rel_floor:
                continue
            unit = units[uid]
            if spent + unit.tokens > budget and kept:
                break
            kept.append(uid)
            spent += unit.tokens
        detail.update(reason="HIGH_MARGIN_SINGLE_PROJECT", kept=len(kept),
                      spent=spent)
        return NARROW, kept, detail
    kept, spent = [], 0
    for uid, _ in present:
        unit = units[uid]
        if spent + unit.tokens > budget and kept:
            break
        kept.append(uid)
        spent += unit.tokens
    detail.update(reason="FLAT_OR_SPREAD", kept=len(kept), spent=spent)
    return BROAD, kept, detail
