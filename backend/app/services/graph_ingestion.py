"""Turn identified source files into a repository's stored code graph.

One ingestion extracts File and Function records, resolves calls, embeds every
function, writes the records in bounded transactions, then clusters the graph
and labels its communities. Progress is reported on the shared ingestion scale.
"""

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.db.gds_ops import run_leiden_clustering
from app.db.graph_ops import DEFAULT_BATCH_SIZE, open_repository_graph_writer
from app.services.community_summarizer import label_and_store_communities
from app.services.embedding_service import (
    EMBEDDING_REQUEST_BATCH_SIZE,
    MAX_CONCURRENT_EMBEDDING_REQUESTS,
    generate_embeddings,
)
from app.services.graph_records import extract_graph_records, resolve_calls
from app.services.parser_service import IdentifiedFile
from app.utils import ingestion_progress
from app.utils.batching import chunk_data
from app.utils.entity_identity import normalize_repository_path
from app.utils.tokens import DEFAULT_TOKEN_MODEL


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestionProgress:
    """One update on the ingestion stream's progress scale."""

    status: str
    progress: int


def _function_embedding_text(function: dict[str, Any]) -> str:
    """Build stable semantic context from currently available AST fields."""

    return (
        f"Function: {function['qualified_name']}\n"
        f"File: {function['file_path']}"
    )


async def _embedded_function_batches(
    functions: list[dict[str, Any]],
) -> AsyncIterator[list[dict[str, Any]]]:
    """Embed each distinct input once, with bounded request prefetch."""

    groups: dict[str, list[dict[str, Any]]] = {}
    for function in functions:
        groups.setdefault(_function_embedding_text(function), []).append(function)
    inputs = iter(chunk_data(list(groups), EMBEDDING_REQUEST_BATCH_SIZE))
    pending: deque[tuple[list[str], asyncio.Task]] = deque()
    try:
        for _ in range(MAX_CONCURRENT_EMBEDDING_REQUESTS):
            batch = next(inputs, None)
            if batch is not None:
                pending.append((batch, asyncio.create_task(generate_embeddings(batch))))
        while pending:
            batch, task = pending.popleft()
            vectors = await task
            yield [
                {**function, "embedding": vector}
                for text, vector in zip(batch, vectors, strict=True)
                for function in groups[text]
            ]
            following = next(inputs, None)
            if following is not None:
                pending.append((following, asyncio.create_task(generate_embeddings(following))))
    finally:
        for _, task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*(task for _, task in pending), return_exceptions=True)


async def ingest_identified_files_with_progress(
    parsed_files: list[IdentifiedFile],
    repo_name: str,
    replace_existing: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    total_repo_tokens: int | None = None,
    deleted_file_paths: list[str] | None = None,
) -> AsyncIterator[IngestionProgress]:
    """Store one repository's files through bounded file, function, and call passes.

    With ``replace_existing`` the repository graph is rebuilt from scratch.
    Otherwise the parsed files and ``deleted_file_paths`` are treated as an
    incremental change set: definitions that disappeared from those files are
    removed, surviving IDs keep their incoming edges, and outgoing calls from
    the changed files are rebuilt. ``total_repo_tokens`` is stored as the
    repository's token baseline when given; a changed-file subset is not one.
    """

    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    stage_started = perf_counter()
    files, functions, function_calls = extract_graph_records(
        parsed_files,
        repo_name,
    )
    changed_paths = [file["path"] for file in files]
    deleted_paths = sorted(
        {normalize_repository_path(path) for path in deleted_file_paths or []}
        - set(changed_paths)
    )
    affected_paths = sorted({*changed_paths, *deleted_paths})
    incremental = not replace_existing and bool(affected_paths)

    async with open_repository_graph_writer(repo_name) as graph:
        existing_definitions: list[dict[str, Any]] = []
        if replace_existing:
            await graph.delete_repository()
        elif affected_paths:
            existing_definitions = await graph.fetch_definitions_outside(
                affected_paths
            )

        calls, external_calls, ambiguous_calls = resolve_calls(
            functions,
            function_calls,
            [*existing_definitions, *functions],
        )
        logger.info(
            "Ingestion %s: prepared %d functions and %d call edges in %.2fs",
            repo_name, len(functions), len(calls) + len(external_calls),
            perf_counter() - stage_started,
        )

        if total_repo_tokens is not None:
            await graph.store_token_baseline(total_repo_tokens, DEFAULT_TOKEN_MODEL)

        if incremental:
            if deleted_paths:
                await graph.delete_files(deleted_paths)
            await graph.delete_stale_functions(
                affected_paths,
                [function["entity_id"] for function in functions],
            )
            await graph.delete_outgoing_calls(changed_paths)

        yield IngestionProgress(
            "Pass 1: Creating Files...",
            ingestion_progress.FILES_STARTED,
        )
        for batch in chunk_data(files, batch_size):
            await graph.write_files(batch)

        yield IngestionProgress(
            "Pass 2: Embedding and Creating Functions...",
            ingestion_progress.FUNCTIONS.start,
        )
        stage_started = perf_counter()
        function_count = 0
        async with aclosing(_embedded_function_batches(functions)) as embedded_batches:
            async for embedded_group in embedded_batches:
                for embedded_batch in chunk_data(embedded_group, batch_size):
                    await graph.write_functions(
                        [
                            {
                                **function,
                                "ambiguous_calls": ambiguous_calls.get(
                                    function["entity_id"], []
                                ),
                            }
                            for function in embedded_batch
                        ]
                    )
                    function_count += len(embedded_batch)
                    yield IngestionProgress(
                        f"Pass 2: Embedding and Creating Functions ({function_count}/{len(functions)})...",
                        ingestion_progress.FUNCTIONS.at(
                            function_count, len(functions)
                        ),
                    )
        logger.info(
            "Ingestion %s: embedded and stored functions in %.2fs",
            repo_name, perf_counter() - stage_started,
        )

        yield IngestionProgress(
            "Pass 3: Mapping Dependencies...",
            ingestion_progress.DEPENDENCIES.start,
        )
        stage_started = perf_counter()
        call_count = 0
        total_calls = len(calls) + len(external_calls)
        for write_calls, records in (
            (graph.write_calls, calls),
            (graph.write_external_calls, external_calls),
        ):
            for batch in chunk_data(records, batch_size):
                await write_calls(batch)
                call_count += len(batch)
                yield IngestionProgress(
                    f"Pass 3: Mapping Dependencies ({call_count}/{total_calls})...",
                    ingestion_progress.DEPENDENCIES.at(call_count, total_calls),
                )
        logger.info(
            "Ingestion %s: stored dependencies in %.2fs",
            repo_name, perf_counter() - stage_started,
        )

        if incremental:
            await graph.delete_orphan_external_functions()

    yield IngestionProgress(
        "Detecting architectural communities...",
        ingestion_progress.COMMUNITY_DETECTION_STARTED,
    )
    stage_started = perf_counter()
    await run_leiden_clustering(repo_name)
    logger.info(
        "Ingestion %s: clustered graph in %.2fs",
        repo_name, perf_counter() - stage_started,
    )
    yield IngestionProgress(
        "Labeling architectural communities...",
        ingestion_progress.COMMUNITY_LABELING_STARTED,
    )
    stage_started = perf_counter()
    await label_and_store_communities(repo_name)
    logger.info(
        "Ingestion %s: labeled communities in %.2fs",
        repo_name, perf_counter() - stage_started,
    )
    yield IngestionProgress(
        "Completing transaction...",
        ingestion_progress.COMMITTING,
    )


async def ingest_identified_files(
    parsed_files: list[IdentifiedFile],
    repo_name: str,
    replace_existing: bool = False,
    total_repo_tokens: int | None = None,
    deleted_file_paths: list[str] | None = None,
) -> None:
    """Store identified files while discarding progress updates."""

    async for _ in ingest_identified_files_with_progress(
        parsed_files,
        repo_name,
        replace_existing=replace_existing,
        total_repo_tokens=total_repo_tokens,
        deleted_file_paths=deleted_file_paths,
    ):
        pass
