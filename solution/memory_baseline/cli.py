"""Command line: init, ingest, health, search, ask, evaluate, report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import BaselineConfig
from .embeddings import (
    HashingEmbedder,
    OllamaEmbeddingProvider,
    SentenceTransformerProvider,
)
from .evaluation import (
    CONDITIONS,
    metric_means,
    run_condition,
    run_stamped_id,
    save_run,
)
from .health import check_health
from .pipeline import Baseline


def build_embedder(config: BaselineConfig):
    provider = config.embedding.provider
    if provider == "ollama":
        return OllamaEmbeddingProvider(
            config.embedding.model, config.embedding.ollama_host
        )
    if provider == "sentence-transformers":
        return SentenceTransformerProvider(config.embedding.model)
    if provider == "hashing":
        return HashingEmbedder(config.embedding.dimension)
    raise ValueError(f"unknown embedding provider: {provider}")


def build_baseline(config: BaselineConfig) -> Baseline:
    return Baseline(config, build_embedder(config))


def load_tasks(path: Path):
    from memory_measurement.tasks import MemoryTask

    payload = json.loads(path.read_text(encoding="utf-8"))
    return [MemoryTask(**item) for item in payload["tasks"]], payload


def cmd_init(args: argparse.Namespace) -> int:
    baseline = build_baseline(BaselineConfig.from_env())
    baseline.initialise()
    print(f"initialised schema '{baseline.config.schema}'")
    baseline.close()
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    baseline = build_baseline(BaselineConfig.from_env())
    baseline.initialise()
    report = baseline.refresh(Path(args.path))
    print(f"discovered: {report.discovered}")
    print(f"indexed:    {report.indexed} "
          f"(+{report.added} new, ~{report.changed} changed)")
    print(f"unchanged:  {report.unchanged}")
    print(f"removed:    {report.removed}")
    print(f"chunks:     {report.chunks}")
    for failed in report.failed:
        print(f"failed:     {failed}")
    baseline.close()
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    baseline = build_baseline(BaselineConfig.from_env())
    print(check_health(baseline).render())
    print(f"embedding:  {baseline.embedding_version}")
    baseline.close()
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    baseline = build_baseline(BaselineConfig.from_env())
    trace = baseline.retriever.retrieve(args.query)
    for chunk in trace.reranked[: args.k]:
        print(f"[{chunk.rank}] {chunk.source_id} "
              f"(score {chunk.score:.3f}) :: {chunk.text[:200]}")
    baseline.close()
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    baseline = build_baseline(BaselineConfig.from_env())
    result = baseline.ask(args.query)
    print(result.answer.text)
    print(f"\nabstained: {result.answer.abstained}")
    print("admitted:", [c.source_id for c in result.context.admitted])
    print("cited:", result.answer.cited_source_ids)
    baseline.close()
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    from memory_measurement.tasks import MemoryTask  # noqa: F401

    config = BaselineConfig.from_env()
    baseline = build_baseline(config)
    tasks, bundle = load_tasks(Path(args.tasks))
    history_ids = list(bundle.get("history_source_ids", []))
    run_id = args.run_id or run_stamped_id()
    conditions = args.conditions.split(",") if args.conditions else list(
        CONDITIONS
    )
    runs_root = Path(args.runs_root)
    for condition in conditions:
        cases, summary = run_condition(
            condition, tasks, baseline, history_ids
        )
        run_dir = save_run(
            run_id,
            args.system_name,
            condition,
            {
                "corpus_version": bundle.get("corpus_version", "unspecified"),
                "task_set_version": bundle.get(
                    "task_set_version", "unspecified"
                ),
                "model_identity": config.generator.provider,
                "model_version": config.generator.model,
                "notes": args.notes,
            },
            config,
            cases,
            runs_root,
        )
        means = metric_means(cases)
        print(f"== {condition} -> {run_dir}")
        for metric, value in means.items():
            print(f"   {value!s:>6}  {metric}")
    baseline.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memory-baseline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("path")
    ingest.set_defaults(func=cmd_ingest)
    sub.add_parser("health").set_defaults(func=cmd_health)
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--k", type=int, default=8)
    search.set_defaults(func=cmd_search)
    ask = sub.add_parser("ask")
    ask.add_argument("query")
    ask.set_defaults(func=cmd_ask)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--tasks", required=True)
    evaluate.add_argument("--runs-root", required=True)
    evaluate.add_argument("--system-name", default="rag-baseline")
    evaluate.add_argument("--conditions", default="")
    evaluate.add_argument("--run-id", default="")
    evaluate.add_argument("--notes", default="")
    evaluate.set_defaults(func=cmd_evaluate)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
