"""Measure the real ingestion pipeline against an explicitly selected database.

Uses live GitHub/OpenAI calls and replaces the requested repository's graph.
Run against a disposable Neo4j instance with GDS, never a shared database.
"""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def benchmark(args):
    os.environ["NEO4J_URI"] = args.neo4j_uri
    if args.cache_path is not None:
        os.environ["EMBEDDING_CACHE_PATH"] = args.cache_path

    from app import main
    from app.config import settings
    from app.db import close_neo4j_driver, fetch_node_code, get_neo4j_driver
    from app.db.neo4j_client import close_driver, initialize_database
    from app.services import community_summarizer, embedding_service

    args.output.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(args.output.with_suffix(".log")), level=logging.INFO, force=True)
    await asyncio.to_thread(initialize_database)
    stats = {
        "repo_name": args.repo,
        "timing_scope": "download, parse, embeddings, graph writes, GDS, community labels, cleanup",
        "embedding_cache_was_empty": not Path(settings.EMBEDDING_CACHE_PATH).exists() if settings.EMBEDDING_CACHE_PATH else True,
        "embedding_requests": 0, "embedding_inputs": 0,
        "embedding_input_tokens": 0, "label_requests": 0,
    }
    unique_inputs = set()
    embedding_create = embedding_service._get_embedding_client().embeddings.create

    async def counted_embeddings(*call_args, **kwargs):
        stats["embedding_requests"] += 1
        stats["embedding_inputs"] += len(kwargs["input"])
        unique_inputs.update(kwargs["input"])
        result = await embedding_create(*call_args, **kwargs)
        stats["embedding_input_tokens"] += result.usage.total_tokens
        return result

    embedding_service._get_embedding_client().embeddings.create = counted_embeddings
    label_generate = community_summarizer._generate_community_labels

    async def counted_labels(*call_args, **kwargs):
        stats["label_requests"] += 1
        return await label_generate(*call_args, **kwargs)

    community_summarizer._generate_community_labels = counted_labels
    download = main.download_and_extract_repo

    async def measured_download(*call_args, **kwargs):
        root = await download(*call_args, **kwargs)
        stats["archive_root_name"] = Path(root).name
        return root

    main.download_and_extract_repo = measured_download
    started = perf_counter()
    stage = None
    last_print = 0
    stats["stages"] = []
    try:
        async for line in main._stream_repository_ingestion(*args.repo.split("/")):
            record = json.loads(line)
            elapsed = perf_counter() - started
            status = record["status"]
            key = status.split(" (")[0]
            if status.startswith("Pass "):
                key = status.split(":")[0]
            if key != stage:
                stats["stages"].append({"seconds": round(elapsed, 3), "status": status})
            if key != stage or elapsed - last_print >= 10 or "error" in record:
                print(f"{elapsed:.2f}s {status}", flush=True)
                last_print = elapsed
            stage = key
            stats["final_record"] = record
        stats["total_seconds"] = round(perf_counter() - started, 3)
        stats["distinct_embedding_inputs"] = len(unique_inputs)
        if stats["final_record"].get("progress") != 100:
            raise RuntimeError("Ingestion did not complete")

        async with get_neo4j_driver().session() as session:
            result = await session.run(
                "MATCH (f:Function {repo_name:$repo}) "
                "OPTIONAL MATCH (file:File {repo_name:$repo})-[:DEFINES]->(f) "
                "RETURN count(DISTINCT f) AS functions, count(DISTINCT f.entity_id) AS unique_functions, "
                "count(DISTINCT CASE WHEN f.embedding IS NOT NULL THEN f END) AS embedded_functions, "
                "count(file) AS defines_links, "
                "sum(CASE WHEN file IS NULL OR file.path <> f.file_path THEN 1 ELSE 0 END) AS invalid_defines, "
                "sum(CASE WHEN f.embedding IS NULL OR size(f.embedding) <> 1536 THEN 1 ELSE 0 END) AS invalid_vectors, "
                "count(DISTINCT CASE WHEN f.has_body THEN [f.file_path, f.name] END) AS previous_embedding_inputs",
                repo=args.repo,
            )
            stats["persisted"] = dict(await result.single())
            result = await session.run(
                "MATCH (f:Function {repo_name:$repo}) WHERE NOT (f)-[:IN_COMMUNITY]->(:Community) "
                "RETURN count(f) AS missing_communities", repo=args.repo,
            )
            stats["missing_communities"] = (await result.single())["missing_communities"]
            result = await session.run(
                "MATCH (f:Function {repo_name:$repo}) "
                "RETURN elementId(f) AS node_id, f.raw_code AS code, f.file_path AS path LIMIT 2",
                repo=args.repo,
            )
            samples = await result.data()
        for sample in samples:
            source = await fetch_node_code(sample["node_id"], args.repo)
            assert source["code"] == sample["code"] and source["file_path"] == sample["path"]
        stats["source_samples_verified"] = len(samples)
        persisted = stats["persisted"]
        assert persisted["functions"] > 0
        assert persisted["functions"] == persisted["unique_functions"] == persisted["embedded_functions"] == persisted["defines_links"]
        assert persisted["invalid_defines"] == persisted["invalid_vectors"] == stats["missing_communities"] == 0
        if args.require_under is not None and stats["total_seconds"] >= args.require_under:
            raise RuntimeError(f"Ingestion exceeded {args.require_under} seconds")
    finally:
        args.output.write_text(json.dumps(stats, indent=2) + "\n")
        print(json.dumps(stats, indent=2), flush=True)
        await close_neo4j_driver()
        close_driver()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="tiangolo/fastapi")
    parser.add_argument("--neo4j-uri", required=True)
    parser.add_argument("--cache-path")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-under", type=float)
    arguments = parser.parse_args()
    if len(arguments.repo.split("/")) != 2 or not all(arguments.repo.split("/")):
        parser.error("--repo must be owner/repository")
    asyncio.run(benchmark(arguments))
