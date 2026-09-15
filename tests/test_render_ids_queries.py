"""Render + IDs + queries + oracle tests."""

import hashlib

from generator import build
from generator.worlds import build_ledger

SEED = 20240823


def _built():
    return build.build_corpus(seed=SEED, n_worlds=12)


def test_world_a_display_ids_exact():
    ledger, _, _ = build_ledger(12, seed=SEED)
    ids = {r.display_id for r in ledger.records}
    for did in ("adr-003", "adr-007", "adr-009", "session-031", "session-033",
                "session-040", "session-044", "runbook-006",
                "deployment-001", "deployment-101"):
        assert did in ids, did


def test_suffixes_globally_unique():
    b = _built()
    suffixes = []
    for art in b["artifacts"]:
        suffixes.append(int(art.display_id.rsplit("-", 1)[1]))
    assert len(suffixes) == len(set(suffixes))


def test_gen_ids_monotonic_and_unique():
    b = _built()
    gen_ids = [a.internal_id for a in b["artifacts"]]
    assert len(set(gen_ids)) == len(gen_ids)
    nums = [int(g.split("-")[1]) for g in gen_ids]
    assert nums == sorted(nums)
    assert nums[0] == 1


def test_decision_styles_all_present():
    b = _built()
    styles = {m["render_style"] for m in b["build_meta"]
              if m["kind"] == "decision"}
    assert styles == {"crisp", "buried", "split"}


def test_split_decision_yields_two_artifacts_sharing_key():
    b = _built()
    split_keys = [m["record_key"] for m in b["build_meta"]
                  if m["render_style"] == "split"]
    assert split_keys, "no split decisions rendered"
    for key in set(split_keys):
        arts = [a for a in b["artifacts"] if key in a.record_keys]
        assert len(arts) == 2
        assert arts[0].display_id != arts[1].display_id


def test_body_hygiene():
    from generator.render import check_body_hygiene
    b = _built()
    assert check_body_hygiene(b["artifacts"]) == []


def test_q2_decision_resolution_world_a():
    from generator import queries as qmod
    ledger, _, _ = build_ledger(12, seed=SEED)
    by_display = {}
    ans, _ = qmod.q2_decision_expected(ledger, "event-store backend", "2024-07-10")
    assert ans["decision"] == "Use SQLite for the first production event store."
    assert ans["status"] == "current"
    ans, _ = qmod.q2_decision_expected(ledger, "event-store backend", "2024-07-15")
    assert ans["decision"] == "New event-store work should target PostgreSQL."
    assert ans["status"] == "current"


def test_q2_production_as_of_semantics():
    from generator import queries as qmod
    ledger, _, _ = build_ledger(12, seed=SEED)
    ans, _ = qmod.q2_production_expected(ledger, "event-store backend", "2024-07-15")
    assert ans["production"] == "SQLite runs in production."
    ans, _ = qmod.q2_production_expected(ledger, "event-store backend", "2024-07-22")
    assert ans["production"] == "PostgreSQL runs in production."


def test_every_query_has_as_of_and_family():
    b = _built()
    assert b["queries"], "no queries built"
    for q in b["queries"]:
        assert q.as_of and q.family in ("Q1", "Q2-decision", "Q2-production")


def test_oracle_exact_and_hash_matched():
    b = _built()
    exp_by_q = {e.query_id: e for e in b["expected"]}
    assert len(b["oracle"]) == sum(
        1 for q in b["queries"] if q.family.startswith("Q2"))
    for entry in b["oracle"]:
        exp = exp_by_q[entry["query_id"]]
        assert {p["display"] for p in entry["passages"]} == set(exp.supporting)
        for p in entry["passages"]:
            art = b["by_display"][p["display"]]
            assert p["body_sha256"] == hashlib.sha256(
                art.body.encode("utf-8")).hexdigest()


def test_oracle_preference_role_and_evaluator_side(tmp_path):
    b = _built()
    roles = {p["display"]: p["role"]
             for e in b["oracle_roles"] for p in e["passages"]}
    assert roles["session-033"] == "preference"
    assert roles["adr-007"] == "decision"
    # evaluator files must not live under corpus/
    out = tmp_path / "frozen"
    build.write_corpus(b, out)
    assert not (out / "corpus" / "eval").exists()
    assert (out / "eval" / "oracle.jsonl").exists()
