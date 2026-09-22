"""Version-pinned bridge to Microsoft's public query API, in its own runtime.

The CLI only prints an answer. This worker also preserves the returned
context tables, so the book never infers retrieval from query-word overlap.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
from pathlib import Path


async def query(root: Path, mode: str, question: str, level: int):
    import graphrag.api as api
    from graphrag.config.load_config import load_config
    from graphrag.data_model.data_reader import DataReader
    from graphrag_storage import create_storage
    from graphrag_storage.tables.table_provider_factory import create_table_provider

    config = load_config(root_dir=root)
    provider = create_table_provider(config.table_provider, storage=create_storage(config.output_storage))
    reader = DataReader(provider)
    names = {
        "basic": ["text_units"],
        "global": ["entities", "communities", "community_reports"],
        "local": ["entities", "communities", "community_reports", "text_units", "relationships"],
        "drift": ["entities", "communities", "community_reports", "text_units", "relationships"],
    }[mode]
    args = {name: await getattr(reader, name)() for name in names}
    if mode == "local":
        args["covariates"] = await reader.covariates() if await provider.has("covariates") else None
    if mode != "basic":
        args["community_level"] = level
    if mode == "global":
        args["dynamic_community_selection"] = False
    return await getattr(api, mode + "_search")(
        config=config, query=question, response_type="Multiple Paragraphs", **args)


def serialise(value):
    import pandas as pd
    if isinstance(value, pd.DataFrame):
        return json.loads(value.to_json(orient="records"))
    if isinstance(value, dict):
        return {str(k): serialise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialise(v) for v in value]
    if hasattr(value, "tolist"):
        return serialise(value.tolist())
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--mode", choices=["basic", "local", "global", "drift"], required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--level", type=int, default=2)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    actual = importlib.metadata.version("graphrag")
    if actual != args.version:
        raise RuntimeError(f"GraphRAG version mismatch: expected {args.version}, installed {actual}")
    answer, context = asyncio.run(query(args.root, args.mode, args.question, args.level))
    args.output.write_text(json.dumps({"answer": answer, "context": serialise(context),
                                      "graphrag_version": actual}, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
