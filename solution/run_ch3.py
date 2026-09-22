"""Chapter 3 measurement driver: honest runs, frozen artifacts.

Produces genuine book results on the ch3 fixture corpus:
  1. embedding comparison (retrieval-only, no generator involved);
  2. chunking-policy comparison (retrieval-only);
  3. full ladder no-memory/lexical/dense/hybrid/hybrid-reranked/best/
     oracle/full-history with a real reader;
  4. reader-strength comparison on oracle + best conditions;
  5. context-budget sweep.

Every run is persisted under experiments/benchmark/runs/<run-id>/ with
manifest, config snapshot, and per-case records. Small fixture (10
tasks): indicative, not conclusive — the chapter says so.

Usage from the solution directory:
  python run_ch3.py [--skip-embeddings] [--skip-ladder] [--reader MODEL]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SOLUTION_ROOT))

from memory_baseline.cli import load_tasks  # noqa: E402
from memory_baseline.config import (  # noqa: E402
    BaselineConfig,
    ChunkingConfig,
    ContextConfig,
    EmbeddingConfig,
    GeneratorConfig,
    RetrievalConfig,
)
from memory_baseline.embeddings import (  # noqa: E402
    OllamaEmbeddingProvider,
    SentenceTransformerProvider,
)
from memory_baseline.evaluation import (  # noqa: E402
    metric_means,
    run_condition,
    run_stamped_id,
    save_run,
)
from memory_baseline.generation import ExtractiveReader  # noqa: E402
from memory_baseline.health import check_health  # noqa: E402
from memory_baseline.pipeline import Baseline  # noqa: E402
from memory_baseline.retrieval import Retriever  # noqa: E402

RUNS_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark" / "runs"
FIXTURES = SOLUTION_ROOT / "fixtures" / "history"
TASKS_FILE = SOLUTION_ROOT / "fixtures" / "tasks.json"

EMBEDDING_CANDIDATES = [
    ("ollama", "bge-m3"),
    ("ollama", "nomic-embed-text"),
    ("ollama", "mxbai-embed-large"),
    ("ollama", "all-minilm:l6-v2"),
    ("ollama", "qwen3-embedding:8b"),
    ("sentence-transformers", "sentence-transformers/all-MiniLM-L6-v2"),
]


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
            cwd=str(SOLUTION_ROOT.parent),
        )
        return out.stdout.strip() or "unspecified"
    except Exception:
        return "unspecified"


def build_embedder(provider: str, model: str):
    if provider == "ollama":
        return OllamaEmbeddingProvider(model)
    return SentenceTransformerProvider(model)


def slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_")[:40]


def retrieval_only_eval(tasks, baseline, modes=("lexical", "dense", "hybrid")):
    """Source recall/precision per task without involving the generator."""
    from memory_measurement.scorers import source_precision, source_recall
    from memory_measurement.tasks import SystemOutput

    out = {}
    for mode in modes:
        retriever = Retriever(
            baseline.store, baseline.embedder,
            RetrievalConfig(mode=mode, reranker="none"),
        )
        recalls, precisions = [], []
        for task in tasks:
            trace = retriever.retrieve(task.prompt)
            top = trace.fused[:8]
            seen = [c.source_id for c in top]
            output = SystemOutput(
                task_id=task.task_id, retrieved_ids=tuple(seen)
            )
            recalls.append(source_recall(task, output).value)
            precisions.append(source_precision(task, output).value)
        out[mode] = {
            "source_recall@8": sum(recalls) / len(recalls),
            "source_precision@8": sum(precisions) / len(precisions),
        }
    return out


def main() -> int:
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument("--skip-embeddings", action="store_true")
    args_parser.add_argument("--skip-ladder", action="store_true")
    args_parser.add_argument("--reader", default="llama3.1:8b")
    args_parser.add_argument("--run-id", default="")
    cli = args_parser.parse_args()

    tasks, bundle = load_tasks(TASKS_FILE)
    history_ids = list(bundle["history_source_ids"])
    run_id = cli.run_id or run_stamped_id("ch3")
    print(f"run id: {run_id}")
    summary: dict = {
        "run_id": run_id,
        "code_commit": git_commit(),
        "corpus_version": bundle["corpus_version"],
        "task_set_version": bundle["task_set_version"],
    }

    # -- 1. embedding comparison -------------------------------------
    if not cli.skip_embeddings:
        comparison = {}
        for provider, model in EMBEDDING_CANDIDATES:
            name = f"{provider}/{model}"
            schema = "ch3_emb_" + slug(model)
            try:
                started = time.perf_counter()
                embedder = build_embedder(provider, model)
                probe_dim = embedder.embed(["probe"]).dimension
                config = BaselineConfig(
                    schema=schema,
                    embedding=EmbeddingConfig(
                        provider=provider, model=model,
                        dimension=probe_dim,
                    ),
                )
                baseline = Baseline(config, embedder)
                baseline.initialise()
                report = baseline.refresh(FIXTURES)
                health = check_health(baseline)
                scores = retrieval_only_eval(tasks, baseline)
                comparison[name] = {
                    "embedding_version": embedder.version(),
                    "dimension": embedder.embed(["probe"]).dimension,
                    "healthy": health.healthy,
                    "chunks": report.chunks,
                    "seconds": round(time.perf_counter() - started, 1),
                    **scores,
                }
                print(f"[emb] {name}: {scores['hybrid']}")
                baseline.close()
            except Exception as exc:
                comparison[name] = {"error": f"{type(exc).__name__}: {exc}"}
                print(f"[emb] {name}: FAILED {exc}")
        summary["embedding_comparison"] = comparison

        # -- 2. chunking comparison (default embedding) --------------
        chunking = {}
        for policy in ("fixed", "sentence", "section"):
            schema = f"ch3_chunk_{policy}"
            try:
                embedder = build_embedder("ollama", "bge-m3")
                config = BaselineConfig(
                    schema=schema,
                    chunking=ChunkingConfig(policy=policy),
                )
                baseline = Baseline(config, embedder)
                baseline.initialise()
                baseline.refresh(FIXTURES)
                chunking[policy] = retrieval_only_eval(tasks, baseline)
                print(f"[chunk] {policy}: {chunking[policy]['hybrid']}")
                baseline.close()
            except Exception as exc:
                chunking[policy] = {"error": str(exc)}
        summary["chunking_comparison"] = chunking

    # -- 3-5. ladder, readers, budgets -------------------------------
    if not cli.skip_ladder:
        schema = "ch3_ladder"
        config = BaselineConfig(
            schema=schema,
            generator=GeneratorConfig(model=cli.reader),
        )
        baseline = Baseline(config, build_embedder("ollama", "bge-m3"))
        baseline.initialise()
        report = baseline.refresh(FIXTURES)
        health = check_health(baseline)
        print(f"[ladder] indexed={report.indexed} "
              f"healthy={health.healthy}")
        assert health.healthy, [i.detail for i in health.issues]

        ladder = {}
        for condition in ("no-memory", "lexical", "dense", "hybrid",
                          "hybrid-reranked", "best", "oracle",
                          "full-history"):
            cases, _ = run_condition(condition, tasks, baseline, history_ids)
            run_dir = save_run(
                run_id, f"rag-baseline-{cli.reader}", condition,
                {
                    "corpus_version": bundle["corpus_version"],
                    "task_set_version": bundle["task_set_version"],
                    "model_identity": "ollama",
                    "model_version": cli.reader,
                    "code_commit": summary["code_commit"],
                    "notes": "Chapter 3 fixture run; n=10 tasks.",
                },
                config, cases, RUNS_ROOT,
            )
            ladder[condition] = {
                "run_dir": str(run_dir),
                "means": metric_means(cases),
            }
            means = ladder[condition]["means"]
            print(f"[{condition}] decision={means.get('decision_exactness')} "
                  f"recall={means.get('source_recall')} "
                  f"current={means.get('current_state_accuracy')}")
        summary["ladder"] = ladder

        # reader strength on oracle + best
        readers = {}
        for reader_model in ("llama3.1:8b", "mistral-small:latest"):
            if reader_model == cli.reader:
                continue
            reader_config = BaselineConfig(
                schema=schema,
                generator=GeneratorConfig(model=reader_model),
            )
            reader_baseline = Baseline(
                reader_config, build_embedder("ollama", "bge-m3")
            )
            per_condition = {}
            for condition in ("best", "oracle"):
                cases, _ = run_condition(
                    condition, tasks, reader_baseline, history_ids
                )
                per_condition[condition] = metric_means(cases)
            readers[reader_model] = per_condition
            print(f"[reader {reader_model}] {per_condition}")
            reader_baseline.close()
        summary["reader_strength"] = readers

        # budget sweep on best condition: answer-stage effects, not just
        # retrieval recall (retrieval is budget-independent by design).
        budgets = {}
        for label, context in [
            ("small", ContextConfig(max_chars=2000, max_passages=3)),
            ("large", ContextConfig(max_chars=12000, max_passages=12)),
        ]:
            per_task = []
            for task in tasks:
                result = baseline.ask(task.prompt, context_override=context)
                per_task.append((task, result))
            from memory_baseline.evaluation import _to_system_output
            from memory_measurement.scorers import score_task

            recalls, decisions, admitted = [], [], []
            for task, result in per_task:
                chunk_to_source = {
                    c.chunk_id: c.source_id
                    for c in result.context.admitted
                }
                output = _to_system_output(
                    task, result, chunk_to_source, history_ids
                )
                admitted.append(len(result.context.admitted))
                for obs in score_task(task, output, tuple(history_ids)):
                    if obs.metric == "source_recall":
                        recalls.append(obs.value)
                    if obs.metric == "decision_exactness":
                        decisions.append(1.0 if obs.value else 0.0)
            budgets[label] = {
                "source_recall": sum(recalls) / len(recalls),
                "decision_exactness": (
                    sum(decisions) / len(decisions) if decisions else None
                ),
                "mean_admitted_passages": sum(admitted) / len(admitted),
                "context_chars": context.max_chars,
                "passages": context.max_passages,
            }
            print(f"[budget {label}] {budgets[label]}")
        summary["budgets"] = budgets
        baseline.close()

    out_path = RUNS_ROOT / run_id / "summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True),
                         encoding="utf-8")
    print(f"summary: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
