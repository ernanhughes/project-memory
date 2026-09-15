"""Build determinism + manifest tests."""

from generator import build
from generator import manifest as manifest_mod

SEED = 20240823


def _snapshot(b):
    arts = {a.display_id: a.body for a in b["artifacts"]}
    qs = [(q.query_id, q.text, q.as_of) for q in b["queries"]]
    exp = [(e.query_id, str(e.answer), e.supporting) for e in b["expected"]]
    return arts, qs, exp


def test_same_seed_identical_build():
    assert _snapshot(build.build_corpus(seed=SEED)) == _snapshot(
        build.build_corpus(seed=SEED))


def test_different_seed_differs():
    assert _snapshot(build.build_corpus(seed=SEED)) != _snapshot(
        build.build_corpus(seed=1))


def test_manifest_verifies_after_freeze(tmp_path):
    out = tmp_path / "frozen"
    build.freeze(seed=SEED, n_worlds=12, out=out, repo_root=".")
    assert manifest_mod.verify_manifest(out) == []
    assert (out / "manifest.json").exists()


def test_freeze_aborts_when_audit_fails(tmp_path, monkeypatch):
    import generator.audits as audits_mod
    real = audits_mod.run_all

    def failing(inputs):
        results = real(inputs)
        results[0] = audits_mod.AuditResult(
            results[0].name, False, 99.0, 0.0, "forced failure")
        return results

    monkeypatch.setattr(audits_mod, "run_all", failing)
    try:
        build.freeze(seed=SEED, n_worlds=12, out=tmp_path / "frozen",
                     repo_root=".")
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("freeze did not abort on audit failure")
