"""Command surface for derived memory (book §37, §59 demo).

Commands (from the solution directory, system python):
  python -m graph_memory.cli index [--force] [--chat-model M] [--embed-model E]
  python -m graph_memory.cli health
  python -m graph_memory.cli inspect [--entity NAME] [--claims-for NAME] [--community ID] [--counts]
  python -m graph_memory.cli query "question" [--mode local|global|drift|basic]
  python -m graph_memory.cli compare "question" [--reader-model M]

The GraphRAG CLI itself is invoked through the configured executable
(normally solution/.venv); this CLI never requires graphrag importable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))

from graph_memory.config import GraphMemoryConfig  # noqa: E402
from graph_memory.evaluation.adapter import (  # noqa: E402
    GraphMemorySystem,
    link_entities,
)
from graph_memory.graphrag_backend.microsoft import (  # noqa: E402
    MicrosoftGraphRAGBackend,
)
from graph_memory.health.checks import check_health  # noqa: E402
from graph_memory.provenance.mapping import build_report  # noqa: E402


def _backend(args) -> MicrosoftGraphRAGBackend:
    overrides = {}
    if getattr(args, "chat_model", None):
        overrides["chat_model"] = args.chat_model
    if getattr(args, "embed_model", None):
        overrides["embedding_model"] = args.embed_model
    return MicrosoftGraphRAGBackend(GraphMemoryConfig.from_env(**overrides))


def cmd_index(args) -> int:
    backend = _backend(args)
    report = backend.index(force=args.force)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    snapshot = backend.snapshot()
    print(f"entities={len(snapshot.entities)} "
          f"relationships={len(snapshot.relationships)} "
          f"claims={len(snapshot.claims)} "
          f"communities={len(snapshot.communities)}")
    for failure in report.failures:
        print(f"FAILURE: {failure}")
    return 0 if not report.failures else 1


def cmd_health(args) -> int:
    backend = _backend(args)
    health = check_health(backend)
    print(health.report_text(backend.manifest()))
    return 0 if health.healthy else 1


def cmd_inspect(args) -> int:
    backend = _backend(args)
    snapshot = backend.snapshot()
    if args.counts:
        print(json.dumps(
            {
                "documents": snapshot.documents,
                "text_units": snapshot.text_units,
                "entities": len(snapshot.entities),
                "relationships": len(snapshot.relationships),
                "claims": len(snapshot.claims),
                "communities": len(snapshot.communities),
            },
            indent=2, sort_keys=True,
        ))
        return 0
    if args.entity:
        wanted = args.entity.lower()
        matches = [e for e in snapshot.entities
                   if wanted in e.name.lower()]
        for entity in matches[:20]:
            print(f"- {entity.name} [{entity.kind}] degree={entity.degree}")
            print(f"  {entity.description[:400]}")
            print(f"  text_units: {entity.source_text_units[:8]}")
        if not matches:
            print("no matching entities")
        return 0
    if args.neighbors:
        wanted = args.neighbors.lower()
        names = {e.name for e in snapshot.entities
                 if wanted in e.name.lower()}
        shown = 0
        for rel in snapshot.relationships:
            if rel.source in names or rel.target in names:
                print(f"- {rel.source} -- {rel.target}")
                print(f"  {rel.description[:300]}")
                shown += 1
                if shown >= 30:
                    break
        if not shown:
            print("no relationships touch a matching entity")
        return 0
    if args.claims_for:
        wanted = args.claims_for.lower()
        shown = 0
        for claim in snapshot.claims:
            if wanted in claim.subject.lower() or wanted in claim.description.lower():
                print(f"- [{claim.claim_type}/{claim.status}] {claim.description[:400]}")
                print(f"  subject={claim.subject} units={claim.source_text_units[:8]}")
                shown += 1
                if shown >= 20:
                    break
        if not shown:
            print("no matching claims (claims may be disabled or empty)")
        return 0
    if args.community:
        for community in snapshot.communities:
            if args.community in (community.community_id, community.title):
                print(f"# {community.title} (level {community.level}, "
                      f"size {community.size})")
                print(community.summary[:3000])
                return 0
        print("no matching community")
        return 0
    if args.source:
        from graph_memory.health.checks import _input_manifest

        manifest = _input_manifest(backend)
        report = build_report(backend, snapshot, manifest)
        for chain in report.chains:
            if chain.derived_id == args.source or chain.derived_name == args.source:
                print(json.dumps(chain.to_dict(), indent=2, sort_keys=True))
                return 0
        print("no derived object with that id/name")
        return 0
    # Default: entity/relationship/claim/community samples.
    print(f"## entities ({len(snapshot.entities)} shown up to 30)")
    for entity in snapshot.entities[:30]:
        print(f"- {entity.name} [{entity.kind}]")
    print(f"## relationships ({len(snapshot.relationships)} shown up to 30)")
    for rel in snapshot.relationships[:30]:
        print(f"- {rel.source} -- {rel.target}")
    print(f"## claims ({len(snapshot.claims)} shown up to 20)")
    for claim in snapshot.claims[:20]:
        print(f"- [{claim.claim_type}] {claim.description[:160]}")
    print(f"## communities ({len(snapshot.communities)})")
    for community in snapshot.communities:
        print(f"- {community.community_id}: {community.title} "
              f"(level {community.level}, size {community.size})")
    return 0


def cmd_query(args) -> int:
    backend = _backend(args)
    result = backend.query(args.question, args.mode)
    print(f"[graph:{result.method} {result.wall_seconds}s]")
    print(result.answer_text)
    return 0


def cmd_compare(args) -> int:
    """Same question through Chapter 3 RAG and one graph method side by side."""
    from memory_baseline.cli import load_tasks  # noqa: E402
    from memory_baseline.config import BaselineConfig, GeneratorConfig  # noqa: E402
    from memory_baseline.embeddings import OllamaEmbeddingProvider  # noqa: E402
    from memory_baseline.pipeline import Baseline  # noqa: E402

    backend = _backend(args)
    config = BaselineConfig(
        generator=GeneratorConfig(model=args.reader_model)
    )
    baseline = Baseline(config, OllamaEmbeddingProvider("bge-m3"))
    history_ids = [p.name for p in
                   (SOLUTION_ROOT / "fixtures" / "history").glob("*")
                   if p.is_file()]
    system = GraphMemorySystem(baseline, backend, history_ids)
    from memory_measurement.tasks import MemoryTask

    task = MemoryTask(
        task_id="adhoc", family="adhoc", prompt=args.question,
        history_ref=system.backend.config.corpus_version,
    )
    graph_ask = system.ask(task, args.mode)
    raw = baseline.ask(args.question)
    print("=== Chapter 3 RAG ===")
    print(raw.answer.text)
    print(f"(cited: {raw.answer.cited_source_ids})")
    print()
    print(f"=== GraphRAG ({args.mode}) + same reader ===")
    print(graph_ask.answer_text)
    print(f"(cited: {graph_ask.cited_source_ids})")
    print(f"(linked entities: {graph_ask.linked_entities})")
    print(f"(implicated: {graph_ask.implicated_sources})")
    baseline.close()
    return 0


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="graph-memory")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index")
    p_index.add_argument("--force", action="store_true")
    p_index.add_argument("--chat-model", default="")
    p_index.add_argument("--embed-model", default="")
    p_index.set_defaults(func=cmd_index)

    p_health = sub.add_parser("health")
    p_health.set_defaults(func=cmd_health)

    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("--counts", action="store_true")
    p_inspect.add_argument("--entity", default="")
    p_inspect.add_argument("--neighbors", default="")
    p_inspect.add_argument("--claims-for", default="")
    p_inspect.add_argument("--community", default="")
    p_inspect.add_argument("--source", default="")
    p_inspect.set_defaults(func=cmd_inspect)

    p_query = sub.add_parser("query")
    p_query.add_argument("question")
    p_query.add_argument("--mode", default="local",
                         choices=["basic", "local", "global", "drift"])
    p_query.set_defaults(func=cmd_query)

    p_compare = sub.add_parser("compare")
    p_compare.add_argument("question")
    p_compare.add_argument("--mode", default="local",
                           choices=["basic", "local", "global", "drift"])
    p_compare.add_argument("--reader-model", default="llama3.1:8b")
    p_compare.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
