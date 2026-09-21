"""Frame filters for C5 probes (next5 C5 pass).

A frame here is a fixed kind-filter over views: naive hard framing
admits only matching views (exclusion), C5 soft framing orders
matching views first with no exclusion. The filter set is fixed and
topic-independent; per-topic probe assignment (which filter a probe
uses on a task) is documented in wrong_memory.py. Frame assignment
may use hidden truth — probes are evaluator-side constructs, like
oracle conditions. What the reader sees, and the establishment
strength class, never depend on hidden truth.

Fixed filter map (order matters: first match wins documented
arbitrary picks):

  dev-session    admits session, commit
  record-review  admits adr, issue, runbook
  ops-state      admits deployment, runbook
"""

from __future__ import annotations

FRAME_FILTERS: tuple[tuple[str, frozenset[str]], ...] = (
    ("dev-session", frozenset({"session", "commit"})),
    ("record-review", frozenset({"adr", "issue", "runbook"})),
    ("ops-state", frozenset({"deployment", "runbook"})),
)

FRAME_NAMES = tuple(name for name, _kinds in FRAME_FILTERS)


def kinds_of(frame_name: str) -> frozenset[str]:
    for name, kinds in FRAME_FILTERS:
        if name == frame_name:
            return kinds
    raise ValueError(f"unknown frame {frame_name!r}")


def hard_filter(frame_name: str, views: list[dict]) -> list[dict]:
    """Naive hard framing: exclusion. Order preserved."""
    kinds = kinds_of(frame_name)
    return [v for v in views if v["kind"] in kinds]


def soft_order(frame_name: str, views: list[dict]) -> list[dict]:
    """C5 soft framing: frame-congruent first, no exclusion."""
    kinds = kinds_of(frame_name)
    return sorted(views,
                  key=lambda v: (0 if v["kind"] in kinds else 1,
                                 v["display_id"]))


def decisive_ids(world, topic: str, as_of: str) -> set[str]:
    """Display ids the current decision needs: same rule as the CO
    oracle builder (decision plus second id). Evaluator-side."""
    out: set[str] = set()
    for record in world.ledger.records:
        if (record.topic == topic and record.kind == "decision"
                and record.date <= as_of
                and (record.valid_from or "") <= as_of
                and (record.valid_until is None
                     or as_of < record.valid_until)):
            if record.display_id:
                out.add(record.display_id)
            if record.second_display_id:
                out.add(record.second_display_id)
    return out


def first_filter_covering(decisive: set[str], views: list[dict],
                          want_covered: bool) -> str:
    """Deterministic filter pick for probe construction: the first
    fixed filter keeping every present decisive id (F0 control) or
    none of them (FW test). Probe construction may use hidden truth;
    establishment strength is held constant separately and never
    follows from this pick."""
    by_id = {v["display_id"]: v for v in views}
    present = {d for d in decisive if d in by_id}
    assert present, "probe needs present decisive units"
    for name, _kinds in FRAME_FILTERS:
        kept = {v["display_id"] for v in hard_filter(name, views)}
        if want_covered and present <= kept:
            return name
        if not want_covered and not (present & kept):
            return name
    raise ValueError("no fixed filter satisfies probe shape")
