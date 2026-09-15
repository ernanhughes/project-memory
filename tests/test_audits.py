"""Leakage audit tests: clean build passes; each planted leak is caught.

Clean-build assertions prove the frozen corpus earns its freeze. Each
plant-a-leak test proves the corresponding audit is not vacuous: inject
exactly the leak the audit guards against and require FAIL.
"""

from generator import audits, build
from generator.audits import AuditResult

SEED = 20240823


def _built():
    return build.build_corpus(seed=SEED, n_worlds=12)


def _clean_inputs(tmp_path):
    b = _built()
    build.write_corpus(b, tmp_path)
    ai = b["audit_inputs"]
    ai["corpus_dir"] = tmp_path / "corpus"
    return b, ai


def test_clean_corpus_passes_all_audits(tmp_path):
    _, ai = _clean_inputs(tmp_path)
    results = audits.run_all(ai)
    assert results, "no audits ran"
    failures = [r for r in results if not r.passed]
    assert not failures, [(r.name, r.detail) for r in failures]


def test_planted_query_leak_caught():
    b = _built()
    queries = list(b["queries"])
    victim = next(q for q in queries if q.family == "Q2-decision")
    decision = next(
        r for r in b["ledger"].records
        if r.kind == "decision" and r.topic == victim.topic
    )
    import dataclasses
    leaked = dataclasses.replace(victim, text=f"Is it true that {decision.content}?")
    result = audits.audit_query_lexical_overlap(
        [leaked if q.query_id == victim.query_id else q for q in queries],
        b["ledger"].records,
    )
    assert isinstance(result, AuditResult)
    assert not result.passed, "verbatim ledger label in query went uncaught"


def test_planted_timestamp_leak_caught():
    b = _built()
    arts = [a for a in b["audit_inputs"]["artifacts"]]
    import copy
    arts = [copy.copy(a) for a in arts]
    kinds = b["audit_inputs"]["record_kind_of"]
    victim_kind = "preference"
    assert any(kinds.get(k) == victim_kind for a in arts for k in a.record_keys)
    for a in arts:
        if any(kinds.get(k) == victim_kind for k in a.record_keys):
            a.has_timestamp = False
    result = audits.audit_timestamp_neutrality(arts, kinds)
    assert not result.passed, "kind-systematic datelessness went uncaught"


def test_planted_template_leak_caught():
    b = _built()
    meta = [dict(m) for m in b["audit_inputs"]["build_meta"]]
    for m in meta:
        if m["kind"] == "proposal":
            m["realisation"] = "session-direct"
    result = audits.audit_template_diversity(meta)
    assert not result.passed, "single-realisation kind went uncaught"


def test_planted_ordering_leak_caught():
    rows = [
        {"order_index": i, "gen_number": i + 1, "display_suffix": 2000 + i,
         "kind": "evidence", "template": "t", "authority": "background"}
        for i in range(30)
    ] + [
        {"order_index": 30 + i, "gen_number": 31 + i, "display_suffix": 3000 + i,
         "kind": "decision", "template": "t", "authority": "authoritative"}
        for i in range(30)
    ]
    result = audits.audit_trivial_classifier(rows)
    assert not result.passed, "order-sorted authority went uncaught"


def test_planted_evaluator_leak_caught(tmp_path):
    _, ai = _clean_inputs(tmp_path)
    corpus = ai["corpus_dir"]
    (corpus / "artifacts" / "gen-000001.md").write_text(
        (corpus / "artifacts" / "gen-000001.md").read_text(encoding="utf-8")
        + "\n<!-- supported_by evt-205 -->\n",
        encoding="utf-8",
    )
    (corpus / "notes.txt").write_text("evaluator scratch", encoding="utf-8")
    result = audits.audit_evaluator_separation(corpus)
    assert not result.passed, "evaluator terms in corpus went uncaught"
