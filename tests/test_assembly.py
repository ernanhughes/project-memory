"""Unit tests for the deterministic C7 assembler (model-free)."""

from simulator import assembly as asm


def _v(did, kind="session", body="text", date="2024-08-01",
       title="t"):
    return {"display_id": did, "kind": kind, "date": date,
            "title": title, "body": body, "project": "main"}


def test_select_decisive_only():
    views = [_v("adr-007"), _v("session-014"), _v("session-033")]
    kept, trace = asm.select_decisive(views, {"adr-007"})
    assert [v["display_id"] for v in kept] == ["adr-007"]
    assert trace == {"adr-007": "select.decisive"}


def test_support_overlap_picks_best_tie_breaks_id():
    views = [_v("adr-007"), _v("s-1", body="PostgreSQL backend target"),
             _v("s-2", body="PostgreSQL backend target")]
    kept, trace = asm.select_support_overlap(
        views, {"adr-007"}, "event store backend target")
    assert [v["display_id"] for v in kept] == ["s-1"]
    assert trace["s-1"] == "select.support-overlap"


def test_collapse_drops_redundant_keeps_unique():
    views = [_v("adr-007", kind="adr", body="Target PostgreSQL."),
             _v("rb-echo", kind="runbook",
                body="Target PostgreSQL."),
             _v("rb-new", kind="runbook",
                body="Also rotate the backups.")]
    derived = {"rb-echo": (("adr-007",), "Target PostgreSQL."),
               "rb-new": (("adr-007",), "Also rotate the backups.")}
    kept, trace = asm.collapse_redundant(views, derived)
    assert [v["display_id"] for v in kept] == ["adr-007", "rb-new"]
    assert trace["rb-echo"] == "drop.redundant-echo"
    assert trace["rb-new"] == "keep.unique-claim"


def test_collapse_keeps_ungrounded():
    views = [_v("rb-orphan", kind="runbook", body="Claims things.")]
    derived = {"rb-orphan": (("ghost-1",), "Claims things.")}
    kept, trace = asm.collapse_redundant(views, derived)
    assert [v["display_id"] for v in kept] == ["rb-orphan"]
    assert trace["rb-orphan"] == "keep.ungrounded"


def test_group_order_decisive_support_remainder():
    views = [_v("s-9", date="2024-08-02"), _v("adr-007", kind="adr"),
             _v("s-1", date="2024-06-01")]
    ordered = asm.group_order(views, {"adr-007"}, {"s-1"})
    assert [v["display_id"] for v in ordered] == [
        "adr-007", "s-1", "s-9"]


def test_budget_keeps_decisive_drops_tail():
    views = [_v("adr-007", body="x" * 100),
             _v("big-1", body="y" * 10000),
             _v("big-2", body="z" * 10000)]
    kept, trace = asm.apply_budget(views, {"adr-007"}, budget=500)
    assert [v["display_id"] for v in kept] == ["adr-007"]
    assert trace == {"big-1": "drop.over-budget",
                     "big-2": "drop.over-budget"}


def test_budget_constant_documented():
    assert asm.BUDGET_CHARS == 5000


def test_assembly_inheritance_map_dry():
    from simulator import muse_ladder as ml
    from simulator import run as run_mod
    data = run_mod.build_inputs()
    world, tasks, views = data["world"], data["tasks"], data["views"]
    task = next(t for t in tasks if t.topic == "event-store backend")
    rows = ml.run_assembly_probe(None, "dry", task, views, world,
                                 "test-model", dry_run=True)
    by_cond = {r["condition"]: r for r in rows}
    assert set(by_cond) == {"A0", "A1", "A2", "A3", "A4", "A5", "A6",
                            "AO", "S1", "S2", "S3", "S4"}
    # S2/S3 coincide with A3/A4 by construction: shared live call.
    # (S3 may attach to A0 when A4 collapses nothing: same string.)
    assert by_cond["S2"].get("inherited_from") == "A3"
    s3src = by_cond["S3"].get("inherited_from")
    assert s3src in ("A4", "A0")
    if s3src == "A0":
        assert by_cond["A4"].get("inherited_from") == "A0"
    for r in rows:
        trace = r["assembly_trace"]
        assert trace["candidate_ids"] and trace["ordering"]
        assert trace["context_chars"] > 0


def test_revocation_gap_echo_visible_in_trace():
    # The C6/T7 defect stays visible: an echo admitted over a
    # revoked source keeps its assembly reasons; nothing here
    # claims the revocation problem solved.
    from simulator import muse_ladder as ml
    from simulator import run as run_mod
    data = run_mod.build_inputs()
    world, tasks, views = data["world"], data["tasks"], data["views"]
    task = next(t for t in tasks if t.topic == "event-store backend")
    rows = ml.run_assembly_probe(None, "dry", task, views, world,
                                 "test-model", dry_run=True)
    a4 = next(r for r in rows if r["condition"] == "A4")
    assert "runbook-006" in a4["assembly_trace"]["selected_ids"]
    reasons = a4["assembly_trace"]["reasons"]
    assert "runbook-006" not in reasons or \
        not reasons["runbook-006"].startswith("drop.")
