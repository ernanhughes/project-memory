"""Leakage audits (H1 pipeline gate).

Each audit returns an AuditResult; the build freezes a corpus only if all
pass. Thresholds are set below with a one-line justification each. Every
audit has a companion plant-a-leak test in tests/test_audits.py proving it
catches the leak it guards against.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Thresholds (justified per audit below).
MAX_SHARED_RUN = 5  # longest query/record shared word-run must stay below this
MAX_PRESENCE_SPREAD = 0.15  # max timestamp-presence spread across record kinds
MIN_REALISATIONS = 3  # distinct surface realisations per record kind
MAX_CLASSIFIER_EXCESS = 0.10  # stump accuracy over majority baseline, at most

AUTHORITATIVE = ("decision", "production_state")

EVALUATOR_TERMS = (
    "supported_by",
    "derived_from",
    "supersedes",
    "valid_from",
    "valid_until",
    "oracle",
    "expected",
    "ledger",
    "build_meta",
    "eval/",
)


@dataclass
class AuditResult:
    name: str
    passed: bool
    metric: float
    threshold: float
    detail: str


def _words(text: str) -> list[str]:
    return [w.strip(".,?:;!\"'()").lower() for w in text.split() if w.strip()]


def _longest_shared_run(a: list[str], b: list[str]) -> int:
    joined = "\x00".join(b)
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            best = max(best, k)
    return best


def audit_query_lexical_overlap(queries, records) -> AuditResult:
    """Queries must not repeat ledger labels verbatim (book Ch2 control).

    Metric: longest shared word-run between any query and any record
    content. Threshold 5: topic phrases (2-3 words) and generic verb
    runs ("runs in production", 3 words) legitimately overlap; a 5-word
    run means the query restates a ledger label and a system could match
    strings instead of reconstructing state.
    """
    worst = 0
    worst_case = ""
    contents = [(_words(r.content), r.key) for r in records]
    for q in queries:
        qw = _words(q.text)
        for cw, key in contents:
            run = _longest_shared_run(qw, cw)
            if run > worst:
                worst = run
                worst_case = f"{q.query_id} x {key}"
    return AuditResult(
        "query-lexical-overlap", worst < MAX_SHARED_RUN, float(worst),
        float(MAX_SHARED_RUN), f"worst shared run: {worst} words ({worst_case})",
    )


def audit_timestamp_neutrality(artifacts, record_kind_of) -> AuditResult:
    """Timestamp presence must not predict record kind.

    Metric: max-min presence rate across kinds. Threshold 0.15: sessions
    are absent ~10% by ledger rule while commits/deployments/ADRs are
    always dated, so a small spread is structural; anything larger means
    some kind is systematically undated (a learnable shortcut).
    """
    rates: dict[str, list[int]] = {}
    for art in artifacts:
        for key in art.record_keys:
            kind = record_kind_of.get(key)
            if kind:
                rates.setdefault(kind, []).append(1 if art.has_timestamp else 0)
    if not rates:
        return AuditResult("timestamp-neutrality", False, 1.0, MAX_PRESENCE_SPREAD, "no data")
    means = {k: sum(v) / len(v) for k, v in rates.items()}
    spread = max(means.values()) - min(means.values())
    return AuditResult(
        "timestamp-neutrality", spread <= MAX_PRESENCE_SPREAD, spread,
        MAX_PRESENCE_SPREAD, f"presence by kind: {means}",
    )


def audit_template_diversity(build_meta) -> AuditResult:
    """Every record kind needs >=3 surface realisations in the corpus, each
    used at least once. Threshold 3 comes straight from the H1 brief."""
    by_kind: dict[str, set[str]] = {}
    for entry in build_meta:
        by_kind.setdefault(entry["kind"], set()).add(entry["realisation"])
    thin = {k: sorted(v) for k, v in by_kind.items() if len(v) < MIN_REALISATIONS}
    ok = not thin
    return AuditResult(
        "template-diversity", ok,
        float(min((len(v) for v in by_kind.values()), default=0)),
        float(MIN_REALISATIONS),
        "thin kinds: " + str(thin) if thin else f"kinds covered: {sorted(by_kind)}",
    )


def _stump_accuracy(values: list[float], labels: list[str]) -> float:
    """Best fixed-split accuracy of one feature predicting one label set.

    Candidate splits are the quartiles only — deliberately NOT every
    midpoint. Searching all midpoints overfits N~50 rows and would flag
    noise as signal; a genuinely trivial, usable shortcut must show up
    at a quartile split.
    """
    n = len(values)
    if n == 0:
        return 0.0
    majority = max(labels.count(l) for l in set(labels)) / n
    ordered = sorted(values)
    cuts = {
        ordered[n // 4], ordered[n // 2], ordered[(3 * n) // 4],
    }
    best = majority
    for c in cuts:
        left = [l for v, l in zip(values, labels) if v <= c]
        right = [l for v, l in zip(values, labels) if v > c]
        if not left or not right:
            continue
        ml = max(set(left), key=left.count)
        mr = max(set(right), key=right.count)
        correct = sum(
            1 for v, l in zip(values, labels)
            if (v <= c and l == ml) or (v > c and l == mr)
        )
        best = max(best, correct / n)
    return best


def audit_trivial_classifier(rows) -> AuditResult:
    """No file path / filename / ordering / display-ID pattern may predict
    record kind, scenario template, or authority.

    Rows: dicts with order_index, gen_number, display_suffix, and labels
    kind / template / authority. Metric: worst stump accuracy excess over
    the majority baseline. Threshold 0.10: a single-threshold rule beating
    majority by more than ten points is a usable shortcut, not noise.
    """
    features = ("order_index", "gen_number", "display_suffix")
    label_sets = ("kind", "template", "authority")
    worst_excess = 0.0
    worst_case = ""
    for feat in features:
        for lab in label_sets:
            vals = [r[feat] for r in rows]
            labs = [r[lab] for r in rows]
            majority = max(labs.count(l) for l in set(labs)) / len(labs)
            acc = _stump_accuracy(vals, labs)
            excess = acc - majority
            if excess > worst_excess:
                worst_excess = excess
                worst_case = f"{feat}->{lab} acc={acc:.2f} maj={majority:.2f}"
    return AuditResult(
        "trivial-classifier", worst_excess <= MAX_CLASSIFIER_EXCESS,
        worst_excess, MAX_CLASSIFIER_EXCESS, f"worst: {worst_case}",
    )


def audit_evaluator_separation(corpus_dir: Path) -> AuditResult:
    """Ledger and expected answers unreachable from the rendered corpus dir:
    strict filename allowlist plus a content sweep for evaluator terms."""
    import re

    problems = []
    allowed = re.compile(r"^(artifacts/gen-\d{6}\.md|queries\.jsonl)$")
    for path in sorted(corpus_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(corpus_dir).as_posix()
        if not allowed.match(rel):
            problems.append(f"unexpected file: {rel}")
            continue
        text = path.read_text(encoding="utf-8").lower()
        for term in EVALUATOR_TERMS:
            if term in text:
                problems.append(f"{rel}: contains {term!r}")
    ok = not problems
    return AuditResult(
        "evaluator-separation", ok, float(len(problems)), 0.0,
        "; ".join(problems[:5]) if problems else "corpus dir clean",
    )


def run_all(audit_inputs: dict) -> list[AuditResult]:
    return [
        audit_query_lexical_overlap(audit_inputs["queries"], audit_inputs["records"]),
        audit_timestamp_neutrality(
            audit_inputs["artifacts"], audit_inputs["record_kind_of"]
        ),
        audit_template_diversity(audit_inputs["build_meta"]),
        audit_trivial_classifier(audit_inputs["classifier_rows"]),
        audit_evaluator_separation(audit_inputs["corpus_dir"]),
    ]
