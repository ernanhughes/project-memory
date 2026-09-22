"""The E10 suite.

Everything except the context-construction mechanism is held fixed:
corpus, query, reader model, prompt, and the context token budget. The
ladder C0-C6 changes only how the bundle is built.

Experiments:

``E10-A``  the ladder over every task, context metrics per task
``E10-B``  same query, different goal: bundle divergence
``E10-C``  same query, different project: cross-project leakage
``E10-D``  goal switch against recency
``E10-E``  current versus superseded evidence
``E10-F``  support versus topicality
``E10-G``  echo coalescing: budget freed, provenance kept
``E10-H``  open-loop material conditioned on the work type
``E10-I``  robustness: signal permutation and an irrelevant signal
``E10-J``  frame capture: the cost of the wrong frame
``E10-K``  inferred frames versus declared frames
``E10-L``  answers and failure attribution
``E10-M``  determinism: identical inputs, identical bundle digest
``E10-N``  policy revision by replay, under regression gates
"""

from __future__ import annotations

from dataclasses import replace

from . import fixtures as fx
from . import metrics as M
from .backtest import backtest
from .corpus import corpus, corpus_digest
from .frames import infer_work_frame, keyword_work_frame
from .policy import (CANDIDATE_POOL, DEFAULT_BUDGET_TOKENS, LADDER,
                     POLICY_VERSION, build_context)
from .retrieval import HybridRetriever, OllamaEmbedder

SUITE = "E10-context-frames-v0.1"


class Harness:
    """One retriever, one corpus, reused by every condition and task."""

    def __init__(self, budget: int = DEFAULT_BUDGET_TOKENS,
                 use_embeddings: bool = True, reader=None) -> None:
        self.units_list = corpus()
        self.units = {u.unit_id: u for u in self.units_list}
        embedder = OllamaEmbedder() if use_embeddings else None
        self.retriever = HybridRetriever(self.units_list, embedder)
        self.retriever.warm()
        self.budget = budget
        self.reader = reader

    def build(self, condition: str, task: fx.Task, work=None, frame=None,
              suffix: str = ""):
        work = work or task.work_frame
        frame = frame or fx.PROJECT_FRAMES[work.project_id]()
        trace_id = f"{task.task_id}-{condition}{suffix}"
        return build_context(condition, task.query, frame, work,
                             self.retriever, self.units, self.budget,
                             trace_id=trace_id, task=task)

    def score(self, condition: str, task: fx.Task, work=None, frame=None,
              suffix: str = "") -> tuple[dict, object, object]:
        work = work or task.work_frame
        frame = frame or fx.PROJECT_FRAMES[work.project_id]()
        bundle, trace = self.build(condition, task, work, frame, suffix)
        return M.score_bundle(task, bundle, trace, frame), bundle, trace


# --------------------------------------------------------------------------

def e10_a(h: Harness) -> dict:
    """The ladder, per task, per condition."""
    rows: dict[str, dict] = {}
    for task in fx.all_tasks():
        rows[task.task_id] = {}
        for condition in LADDER:
            scored, _, _ = h.score(condition.name, task)
            rows[task.task_id][condition.name] = scored
    aggregate: dict[str, dict] = {}
    for condition in LADDER:
        keys = ("must_include_recall", "useful_recall", "context_precision",
                "distractor_admission", "harmful_admission",
                "cross_project_leakage", "redundancy_rate",
                "provenance_completeness", "bundle_tokens")
        aggregate[condition.name] = {
            k: round(sum(rows[t][condition.name][k] for t in rows) / len(rows), 4)
            for k in keys}
        aggregate[condition.name]["label"] = condition.label
    return {"per_task": rows, "mean_over_tasks": aggregate}


def e10_b(h: Harness) -> dict:
    """Same corpus, same query, same budget; only the goal changes."""
    pub, arch = fx.T1_PUBLICATION(), fx.T1_ARCHITECTURE()
    out: dict[str, dict] = {}
    for condition in LADDER:
        _, b_pub, _ = h.score(condition.name, pub)
        _, b_arch, _ = h.score(condition.name, arch)
        divergence = M.bundle_divergence(b_pub, b_arch)
        out[condition.name] = {
            "jaccard": divergence["jaccard"],
            "publication_only": divergence["only_left"],
            "architecture_only": divergence["only_right"],
            "shared": divergence["shared"],
            "publication_must_recall": M.score_bundle(
                pub, b_pub, _blank_trace(b_pub), fx.PF_MEMORY_BOOK()
            )["must_include_recall"],
        }
    baseline = out["C0"]["jaccard"]
    full = out["C6"]["jaccard"]
    return {"query": pub.query, "per_condition": out,
            "baseline_jaccard": baseline, "full_jaccard": full,
            "pass": full < baseline,
            "criterion": "the full builder must separate the two goals more "
                         "than query-only retrieval does"}


def _blank_trace(bundle):
    from .model import ContextTrace
    return ContextTrace(trace_id="tmp", condition=bundle.condition,
                        policy_version=POLICY_VERSION, project_frame="",
                        work_frame="", query="", as_of="",
                        budget_tokens=bundle.budget_tokens)


def e10_c(h: Harness) -> dict:
    """Same query, three projects that share the vocabulary."""
    rows: dict[str, dict] = {}
    for project in (fx.MEMORY_BOOK, fx.WRITER, fx.COCODER):
        task = fx.T2(project)
        rows[project] = {}
        for condition in ("C0", "C1", "C2", "C4", "C6"):
            scored, _, _ = h.score(condition, task)
            rows[project][condition] = {
                "cross_project_leakage": scored["cross_project_leakage"],
                "must_include_recall": scored["must_include_recall"],
                "context_precision": scored["context_precision"],
            }
    mean = {c: round(sum(rows[p][c]["cross_project_leakage"]
                         for p in rows) / len(rows), 4)
            for c in ("C0", "C1", "C2", "C4", "C6")}
    return {"per_project": rows, "mean_leakage": mean,
            "pass": mean["C2"] < mean["C0"] and mean["C6"] <= mean["C2"],
            "criterion": "project scope must reduce leakage and the full "
                         "builder must not reintroduce it"}


def e10_d(h: Harness) -> dict:
    """The most recent history is no longer the most useful history."""
    task = fx.T3()
    rows = {}
    for condition in ("C0", "C1", "C4", "C6"):
        scored, bundle, _ = h.score(condition, task)
        recent = [u for u in bundle.unit_ids() if u.startswith("mb-session-intent")]
        rows[condition] = {
            "must_include_recall": scored["must_include_recall"],
            "context_precision": scored["context_precision"],
            "distractor_admission": scored["distractor_admission"],
            "superseded_session_units_admitted": recent,
        }
    return {"per_condition": rows,
            "pass": (rows["C4"]["must_include_recall"]
                     >= rows["C1"]["must_include_recall"]
                     and len(rows["C4"]["superseded_session_units_admitted"])
                     <= len(rows["C1"]["superseded_session_units_admitted"])),
            "criterion": "goal conditioning must not lose to recency when the "
                         "goal has moved on"}


def e10_e(h: Harness) -> dict:
    """A semantically excellent but superseded design must be demoted."""
    task = fx.T4()
    rows = {}
    for condition in ("C0", "C2", "C4", "C5", "C6"):
        scored, bundle, trace = h.score(condition, task)
        stale = "mb-stale-sqlite" in bundle.unit_ids()
        rows[condition] = {
            "harmful_admission": scored["harmful_admission"],
            "stale_unit_admitted": stale,
            "must_include_recall": scored["must_include_recall"],
            "stale_reason": (trace.why("mb-stale-sqlite") or {}).get(
                "reason_codes"),
        }
    return {"per_condition": rows,
            "pass": (rows["C5"]["stale_unit_admitted"] is False
                     and rows["C5"]["must_include_recall"] == 1.0),
            "criterion": "the Chapter 8 signal must remove the superseded "
                         "design without losing the current one"}


def e10_f(h: Harness) -> dict:
    """Topical neighbours must not substitute for supporting evidence."""
    task = fx.T5()
    rows = {}
    for condition in ("C0", "C2", "C4", "C6"):
        scored, bundle, _ = h.score(condition, task)
        rows[condition] = {
            "must_include_recall": scored["must_include_recall"],
            "context_precision": scored["context_precision"],
            "foreign_topical_admitted": [
                u for u in bundle.unit_ids()
                if u in ("wr-evidence-policy", "cc-evidence-refs")],
        }
    return {"per_condition": rows,
            "pass": rows["C4"]["must_include_recall"]
                    >= rows["C0"]["must_include_recall"],
            "criterion": "support for the project's own rule must outrank "
                         "topical resemblance"}


def e10_g(h: Harness) -> dict:
    """Four restatements of one rule must not occupy four slots."""
    task = fx.T6()
    rows = {}
    for condition in ("C0", "C5", "C6"):
        scored, bundle, trace = h.score(condition, task)
        echoes = [u for u in bundle.unit_ids() if u.startswith("mb-echo-")]
        operations = [s for s in trace.stages if s.get("stage") == "coalesce"]
        folded = sum(len(op.get("echo_folded", ()))
                     for stage in operations for op in stage["operations"])
        sources_kept = all(item.source_refs for item in bundle.items)
        rows[condition] = {
            "echo_units_occupying_slots": echoes,
            "echo_units_folded": folded,
            "redundancy_rate": scored["redundancy_rate"],
            "must_include_recall": scored["must_include_recall"],
            "bundle_items": scored["bundle_items"],
            "bundle_tokens": scored["bundle_tokens"],
            "every_item_sourced": sources_kept,
        }
    return {"per_condition": rows,
            "pass": (rows["C6"]["redundancy_rate"] <= rows["C0"]["redundancy_rate"]
                     and rows["C6"]["every_item_sourced"]),
            "criterion": "coalescing reduces repetition while every item keeps "
                         "its sources"}


def e10_h(h: Harness) -> dict:
    """Open loops are important when the work makes them important."""
    release, publication = fx.T7_RELEASE(), fx.T7_PUBLICATION()
    out = {}
    for condition in ("C0", "C4", "C6"):
        _, b_rel, _ = h.score(condition, release)
        _, b_pub, _ = h.score(condition, publication)
        loops_rel = [u for u in b_rel.unit_ids() if u.startswith("mb-loop-")]
        loops_pub = [u for u in b_pub.unit_ids() if u.startswith("mb-loop-")]
        out[condition] = {
            "release_loops": loops_rel, "publication_loops": loops_pub,
            "release_must_recall": M.score_bundle(
                release, b_rel, _blank_trace(b_rel), fx.PF_MEMORY_BOOK()
            )["must_include_recall"],
            "publication_must_recall": M.score_bundle(
                publication, b_pub, _blank_trace(b_pub), fx.PF_MEMORY_BOOK()
            )["must_include_recall"],
            "jaccard": M.jaccard(b_rel.unit_ids(), b_pub.unit_ids()),
        }
    return {"per_condition": out,
            "pass": len(out["C4"]["release_loops"])
                    > len(out["C4"]["publication_loops"]),
            "criterion": "the same question about unfinished work draws "
                         "different evidence under different objectives"}


def e10_i(h: Harness) -> dict:
    """Selection must depend on the frame's content, not its accidents."""
    task = fx.T1_ARCHITECTURE()
    base = task.work_frame
    _, bundle, _ = h.score("C6", task)
    baseline_digest = bundle.digest()

    reversed_signals = replace(base, signals=tuple(reversed(base.signals)),
                               work_frame_id=base.work_frame_id + "-perm")
    _, permuted, _ = h.score("C6", task, work=reversed_signals, suffix="-perm")

    noisy = replace(base, signals=base.signals + (fx.S_NOISE,),
                    work_frame_id=base.work_frame_id + "-noise")
    _, with_noise, _ = h.score("C6", task, work=noisy, suffix="-noise")

    stripped = replace(base, work_type=fx.WT_PUBLICATION,
                       objective="Prepare Chapter 10 for publication.",
                       work_frame_id=base.work_frame_id + "-loadbearing")
    _, changed, _ = h.score("C6", task, work=stripped, suffix="-lb")

    return {
        "baseline_digest": baseline_digest,
        "permuted_digest": permuted.digest(),
        "noise_digest": with_noise.digest(),
        "load_bearing_digest": changed.digest(),
        "permutation_invariant": permuted.digest() == baseline_digest,
        "irrelevant_signal_invariant": with_noise.digest() == baseline_digest,
        "load_bearing_change_detected": changed.digest() != baseline_digest,
        "load_bearing_jaccard": M.jaccard(bundle.unit_ids(),
                                          changed.unit_ids()),
        "pass": (permuted.digest() == baseline_digest
                 and with_noise.digest() == baseline_digest
                 and changed.digest() != baseline_digest),
        "criterion": "reordering signals and adding an unrelated one change "
                     "nothing; changing the objective changes the bundle",
    }


def e10_j(h: Harness) -> dict:
    """Frame capture: what the wrong frame costs, measured not asserted."""
    rows = {}
    pairs = ((fx.T1_ARCHITECTURE(), fx.WT_PUBLICATION),
             (fx.T1_PUBLICATION(), fx.WT_ARCHITECTURE),
             (fx.T7_RELEASE(), fx.WT_PUBLICATION))
    for task, wrong_type in pairs:
        correct, _, _ = h.score("C6", task)
        wrong_frame = replace(task.work_frame, work_type=wrong_type,
                              work_frame_id=task.work_frame.work_frame_id + "-wrong")
        wrong, _, _ = h.score("C6", task, work=wrong_frame, suffix="-wrong")
        baseline, _, _ = h.score("C0", task)
        rows[task.task_id] = {
            "wrong_work_type": wrong_type,
            "correct_must_recall": correct["must_include_recall"],
            "wrong_must_recall": wrong["must_include_recall"],
            "baseline_must_recall": baseline["must_include_recall"],
            "damage_vs_correct": round(
                correct["must_include_recall"] - wrong["must_include_recall"], 4),
            "worse_than_baseline": wrong["must_include_recall"]
                                   < baseline["must_include_recall"],
        }
    return {"per_task": rows,
            "any_worse_than_baseline": any(
                r["worse_than_baseline"] for r in rows.values()),
            "criterion": "reported as a hazard measurement, not a pass/fail: "
                         "a wrong frame can select worse than no frame"}


def e10_k(h: Harness) -> dict:
    """Frames the system infers, against frames a person declared."""
    rows = {}
    for task in fx.all_tasks():
        frame = fx.PROJECT_FRAMES[task.project_id]()
        declared = task.work_frame
        keyword = keyword_work_frame(
            declared.work_frame_id + "-kw", frame, declared.signals,
            declared.as_of, declared.objective)
        entry = {
            "declared_work_type": declared.work_type,
            "keyword_work_type": keyword.work_type,
            "keyword_correct": keyword.work_type == declared.work_type,
        }
        kw_scored, _, _ = h.score("C6", task, work=keyword, suffix="-kw")
        declared_scored, _, _ = h.score("C6", task)
        entry["keyword_must_recall"] = kw_scored["must_include_recall"]
        entry["declared_must_recall"] = declared_scored["must_include_recall"]
        if h.reader is not None and h.reader.available():
            inferred = infer_work_frame(
                declared.work_frame_id + "-llm", frame, declared.signals,
                declared.as_of, h.reader)
            inf_scored, _, _ = h.score("C6", task, work=inferred, suffix="-llm")
            entry["inferred_work_type"] = inferred.work_type
            entry["inferred_objective"] = inferred.objective
            entry["inferred_correct"] = inferred.work_type == declared.work_type
            entry["inferred_must_recall"] = inf_scored["must_include_recall"]
            entry["inferred_provenance_complete"] = (
                inferred.unprovenanced_fields() == ())
        rows[task.task_id] = entry
    n = len(rows)
    summary = {
        "keyword_work_type_accuracy": round(
            sum(1 for r in rows.values() if r["keyword_correct"]) / n, 4),
        "declared_mean_must_recall": round(
            sum(r["declared_must_recall"] for r in rows.values()) / n, 4),
        "keyword_mean_must_recall": round(
            sum(r["keyword_must_recall"] for r in rows.values()) / n, 4),
    }
    if any("inferred_correct" in r for r in rows.values()):
        summary["inferred_work_type_accuracy"] = round(
            sum(1 for r in rows.values() if r.get("inferred_correct")) / n, 4)
        summary["inferred_mean_must_recall"] = round(
            sum(r.get("inferred_must_recall", 0.0)
                for r in rows.values()) / n, 4)
    return {"per_task": rows, "summary": summary,
            "criterion": "reported, not gated: the frame builder is the "
                         "layer's own failure surface"}


def e10_l(h: Harness, conditions: tuple[str, ...] = ("C0", "C4", "C6")) -> dict:
    """Answers under a fixed reader, and where failures were lost."""
    if h.reader is None or not h.reader.available():
        return {"skipped": "no reader service reachable"}
    rows: dict[str, dict] = {}
    for task in fx.all_tasks():
        rows[task.task_id] = {}
        for condition in conditions:
            scored, bundle, trace = h.score(condition, task)
            prompt = h.reader.build_prompt(
                task.work_frame.objective, task.query, bundle.render())
            answer = h.reader.ask(prompt)
            answer_score = M.score_answer(task, answer)
            rows[task.task_id][condition] = {
                "context": scored,
                "answer": answer_score,
                "attribution": M.attribute_failure(task, bundle, trace,
                                                   answer_score),
                "answer_text": answer,
            }
    summary = {}
    for condition in conditions:
        coverages = [rows[t][condition]["answer"]["key_claim_coverage"]
                     for t in rows
                     if rows[t][condition]["answer"]["key_claim_coverage"]
                     is not None]
        summary[condition] = {
            "mean_key_claim_coverage": round(
                sum(coverages) / len(coverages), 4) if coverages else None,
            "mean_forbidden_claim_rate": round(
                sum(rows[t][condition]["answer"]["forbidden_claim_rate"]
                    for t in rows) / len(rows), 4),
            "mean_context_tokens": round(
                sum(rows[t][condition]["context"]["bundle_tokens"]
                    for t in rows) / len(rows), 1),
        }
    return {"per_task": rows, "summary": summary,
            "reader": h.reader.name}


def e10_m(h: Harness) -> dict:
    """Deterministic inputs must produce an identical bundle."""
    task = fx.T1_ARCHITECTURE()
    digests = []
    for _ in range(3):
        _, bundle, _ = h.score("C6", task)
        digests.append(bundle.digest())
    return {"digests": digests, "pass": len(set(digests)) == 1,
            "criterion": "bundle construction is reproducible"}


# --------------------------------------------------------------------------

def run_suite(budget: int = DEFAULT_BUDGET_TOKENS, reader=None,
              use_embeddings: bool = True) -> dict:
    h = Harness(budget=budget, reader=reader, use_embeddings=use_embeddings)
    audit = fx.audit_ledgers()
    suite = {
        "suite": SUITE,
        "policy_version": POLICY_VERSION,
        "corpus_digest": corpus_digest(),
        "corpus_units": len(h.units_list),
        "retriever": h.retriever.describe(),
        "candidate_pool": CANDIDATE_POOL,
        "budget_tokens": budget,
        "ledger_audit": {"unknown_units": audit.unknown_units,
                         "out_of_scope_required": audit.out_of_scope_required,
                         "empty_required": audit.empty_required},
        "experiments": {
            "E10-A": e10_a(h), "E10-B": e10_b(h), "E10-C": e10_c(h),
            "E10-D": e10_d(h), "E10-E": e10_e(h), "E10-F": e10_f(h),
            "E10-G": e10_g(h), "E10-H": e10_h(h), "E10-I": e10_i(h),
            "E10-J": e10_j(h), "E10-K": e10_k(h), "E10-M": e10_m(h),
            "E10-N": backtest(h, fx.PF_MEMORY_BOOK()),
        },
    }
    suite["experiments"]["E10-L"] = e10_l(h)
    return suite
