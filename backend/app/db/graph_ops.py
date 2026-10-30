"""Neo4j persistence operations for parsed source-code relationships.

Functions are keyed by the deterministic CG-002A ``entity_id`` rather than by
their simple names, so same-named definitions in different files, classes, or
lexical scopes remain separate graph nodes.
"""

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator, Iterable, Iterator
from contextlib import aclosing
from dataclasses import dataclass
from time import perf_counter
from typing import Any, TypeVar

from app.db import get_neo4j_driver
from app.db.gds_ops import run_leiden_clustering
from app.services.community_summarizer import label_and_store_communities
from app.services.embedding_service import (
    EMBEDDING_REQUEST_BATCH_SIZE,
    MAX_CONCURRENT_EMBEDDING_REQUESTS,
    generate_embeddings,
)
from app.services.parser_service import IdentifiedFile, IdentifiedFunction
from app.utils.entity_identity import normalize_repository_path
from app.utils.tokens import DEFAULT_TOKEN_MODEL


logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100
BatchItem = TypeVar("BatchItem")

DELETE_REPOSITORY_QUERY = """
MATCH (node)
WHERE (node:Repository OR node:File OR node:Function OR node:ExternalFunction
       OR node:Community)
  AND node.repo_name = $repo_name
DETACH DELETE node
"""

DELETE_ALL_REPOSITORY_GRAPHS_QUERY = """
MATCH (n)
WHERE n.repo_name IS NOT NULL
DETACH DELETE n
"""

FETCH_EXISTING_DEFINITIONS_QUERY = """
MATCH (fn:Function {repo_name: $repo_name})
WHERE fn.entity_id IS NOT NULL
  AND NOT fn.file_path IN $paths
RETURN fn.entity_id AS entity_id,
       fn.name AS name,
       fn.qualified_name AS qualified_name,
       fn.file_path AS file_path
"""

DELETE_FILES_QUERY = """
MATCH (file:File {repo_name: $repo_name})
WHERE file.path IN $paths
DETACH DELETE file
"""

DELETE_STALE_FUNCTIONS_QUERY = """
MATCH (fn:Function {repo_name: $repo_name})
WHERE fn.file_path IN $paths
  AND (fn.entity_id IS NULL OR NOT fn.entity_id IN $entity_ids)
DETACH DELETE fn
"""

DELETE_OUTGOING_CALLS_QUERY = """
MATCH (fn:Function {repo_name: $repo_name})-[call:CALLS]->()
WHERE fn.file_path IN $paths
DELETE call
"""

DELETE_ORPHAN_EXTERNAL_FUNCTIONS_QUERY = """
MATCH (external:ExternalFunction {repo_name: $repo_name})
WHERE NOT ()-[:CALLS]->(external)
DETACH DELETE external
"""

MERGE_FILES_QUERY = """
UNWIND $batch AS file
MERGE (repository:Repository {repo_name: $repo_name})
ON CREATE SET repository.name = $repo_name
MERGE (f:File {path: file.path, repo_name: $repo_name})
SET f.updated_at = datetime()
MERGE (repository)-[:CONTAINS]->(f)
"""

MERGE_REPOSITORY_TOKENS_QUERY = """
MERGE (repository:Repository {repo_name: $repo_name})
SET repository.name = $repo_name,
    repository.total_tokens = $total_tokens,
    repository.tokenizer_model = $tokenizer_model,
    repository.tokens_updated_at = datetime()
"""

MERGE_FUNCTIONS_QUERY = """
UNWIND $batch AS func
MATCH (f:File {path: func.file_path, repo_name: $repo_name})
MERGE (fn:Function {entity_id: func.entity_id, repo_name: $repo_name})
SET fn.name = func.name,
    fn.qualified_name = func.qualified_name,
    fn.file = func.file_path,
    fn.file_path = func.file_path,
    fn.language = func.language,
    fn.signature = func.signature,
    fn.definition_discriminator = func.definition_discriminator,
    fn.start_line = func.start_line,
    fn.end_line = func.end_line,
    fn.start_column = func.start_column,
    fn.end_column = func.end_column,
    fn.raw_code = func.raw_code,
    fn.ambiguous_calls = func.ambiguous_calls,
    fn.embedding = func.embedding,
    fn.external = false,
    fn.is_external = false
MERGE (f)-[:DEFINES]->(fn)
"""

MERGE_CALLS_QUERY = """
UNWIND $batch AS call
MATCH (caller:Function {entity_id: call.caller_id, repo_name: $repo_name})
MATCH (target:Function {entity_id: call.target_id, repo_name: $repo_name})
MERGE (caller)-[relationship:CALLS]->(target)
SET relationship.resolution = call.resolution,
    relationship.call_count = call.call_count,
    relationship.source_file = call.file_path,
    relationship.inferred_from_file_scope = false
"""

MERGE_EXTERNAL_CALLS_QUERY = """
UNWIND $batch AS call
MATCH (caller:Function {entity_id: call.caller_id, repo_name: $repo_name})
MERGE (target:ExternalFunction {name: call.target_name, repo_name: $repo_name})
ON CREATE SET target.external = true,
              target.is_external = true
MERGE (caller)-[relationship:CALLS]->(target)
SET relationship.resolution = 'external',
    relationship.call_count = call.call_count,
    relationship.source_file = call.file_path,
    relationship.inferred_from_file_scope = false
"""


@dataclass(frozen=True, slots=True)
class DatabaseWriteProgress:
    """One database-stage update for the ingestion stream."""

    status: str
    progress: int


def chunk_data(
    data_list: list[BatchItem],
    chunk_size: int = DEFAULT_BATCH_SIZE,
) -> Iterator[list[BatchItem]]:
    """Yield bounded slices so each Neo4j transaction stays small."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    for index in range(0, len(data_list), chunk_size):
        yield data_list[index : index + chunk_size]


def _function_record(
    function: IdentifiedFunction,
    parsed_file: IdentifiedFile,
) -> dict[str, Any]:
    """Build one persisted Function record keyed by its CG-002A identity."""

    return {
        "entity_id": function.entity_id,
        "name": function.name,
        "qualified_name": function.qualified_name,
        "file_path": parsed_file.file_path,
        "language": parsed_file.language,
        "signature": function.signature,
        "definition_discriminator": function.definition_discriminator,
        "start_line": function.start_line,
        "end_line": function.end_line,
        "start_column": function.start_column,
        "end_column": function.end_column,
        "raw_code": function.raw_code,
    }


def _extract_etl_records(
    parsed_files: list[IdentifiedFile],
    repo_name: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], dict[str, list[str]]]:
    """Flatten identified files into File records, Function records, and call names.

    The third value maps each caller ``entity_id`` to the callee names the
    parser attributed to that function's body, in source order.
    """

    files: list[dict[str, str]] = []
    functions: list[dict[str, Any]] = []
    function_calls: dict[str, list[str]] = {}
    seen_files: set[str] = set()

    for parsed_file in parsed_files:
        if parsed_file.repository != repo_name:
            raise ValueError(
                f"{parsed_file.file_path} was identified for repository "
                f"{parsed_file.repository!r}, not {repo_name!r}"
            )
        if parsed_file.file_path not in seen_files:
            seen_files.add(parsed_file.file_path)
            files.append({"path": parsed_file.file_path})

        for function in parsed_file.functions:
            if function.entity_id in function_calls:
                logger.warning(
                    "Skipping duplicate function identity %s in %s",
                    function.qualified_name,
                    parsed_file.file_path,
                )
                continue
            functions.append(_function_record(function, parsed_file))
            function_calls[function.entity_id] = [
                call.name for call in function.calls
            ]

    return files, functions, function_calls


def _append_index(index: dict[Any, list[str]], key: Any, entity_id: str) -> None:
    index.setdefault(key, []).append(entity_id)


def _resolve_calls(
    functions: list[dict[str, Any]],
    function_calls: dict[str, list[str]],
    definitions: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[str]]]:
    """Map call names to Function IDs without collapsing same-named definitions.

    A callee resolves to exactly one definition: first the nearest enclosing
    lexical scope in the caller's file, then a unique same-file name, then a
    unique repository-wide name. Names that never match become external calls;
    names with several equally plausible definitions are recorded as ambiguous
    on the caller instead of being linked to an arbitrary one.
    """

    by_scope: dict[tuple[str, str], list[str]] = {}
    by_file_name: dict[tuple[str, str], list[str]] = {}
    by_name: dict[str, list[str]] = {}
    for definition in definitions:
        entity_id = definition["entity_id"]
        file_path = definition["file_path"]
        name = definition["name"]
        _append_index(by_scope, (file_path, definition["qualified_name"]), entity_id)
        _append_index(by_file_name, (file_path, name), entity_id)
        _append_index(by_name, name, entity_id)

    def resolve(caller: dict[str, Any], name: str) -> tuple[list[str], str]:
        file_path = caller["file_path"]
        scope = caller["qualified_name"].split(".")
        for depth in range(len(scope), -1, -1):
            qualified_name = ".".join([*scope[:depth], name])
            matches = by_scope.get((file_path, qualified_name), [])
            if matches:
                return matches, "lexical_scope"
        matches = by_file_name.get((file_path, name), [])
        if matches:
            return matches, "same_file"
        return by_name.get(name, []), "repository_unique"

    internal: dict[tuple[str, str], dict[str, Any]] = {}
    external: dict[tuple[str, str], dict[str, Any]] = {}
    ambiguous: dict[str, list[str]] = {}
    for caller in functions:
        caller_id = caller["entity_id"]
        for name in function_calls.get(caller_id, []):
            matches, resolution = resolve(caller, name)
            if len(matches) > 1:
                names = ambiguous.setdefault(caller_id, [])
                if name not in names:
                    names.append(name)
                continue
            if matches:
                key = (caller_id, matches[0])
                record = internal.setdefault(
                    key,
                    {
                        "caller_id": caller_id,
                        "target_id": matches[0],
                        "resolution": resolution,
                        "call_count": 0,
                        "file_path": caller["file_path"],
                    },
                )
            else:
                key = (caller_id, name)
                record = external.setdefault(
                    key,
                    {
                        "caller_id": caller_id,
                        "target_name": name,
                        "call_count": 0,
                        "file_path": caller["file_path"],
                    },
                )
            record["call_count"] += 1

    return list(internal.values()), list(external.values()), ambiguous


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


async def save_parsed_ast_to_neo4j_with_progress(
    parsed_files: list[IdentifiedFile],
    repo_name: str,
    replace_existing: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    total_repo_tokens: int | None = None,
    deleted_file_paths: list[str] | None = None,
) -> AsyncIterator[DatabaseWriteProgress]:
    """Persist one repository through bounded file, function, and call passes.

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
    files, functions, function_calls = _extract_etl_records(
        parsed_files,
        repo_name,
    )
    changed_paths = [file["path"] for file in files]
    deleted_paths = sorted(
        {normalize_repository_path(path) for path in deleted_file_paths or []}
        - set(changed_paths)
    )
    affected_paths = sorted({*changed_paths, *deleted_paths})

    async with get_neo4j_driver().session() as session:
        async def run_transaction(
            query: str,
            batch: list[dict[str, Any]] | None = None,
            extra_parameters: dict[str, Any] | None = None,
        ) -> None:
            async def execute(transaction: Any) -> None:
                parameters: dict[str, Any] = {"repo_name": repo_name}
                if batch is not None:
                    parameters["batch"] = batch
                if extra_parameters is not None:
                    parameters.update(extra_parameters)
                result = await transaction.run(query, **parameters)
                await result.consume()

            await session.execute_write(execute)

        existing_definitions: list[dict[str, Any]] = []
        if replace_existing:
            await run_transaction(DELETE_REPOSITORY_QUERY)
        elif affected_paths:
            result = await session.run(
                FETCH_EXISTING_DEFINITIONS_QUERY,
                repo_name=repo_name,
                paths=affected_paths,
            )
            existing_definitions = [
                record
                for record in await result.data()
                if all(
                    isinstance(record.get(key), str)
                    for key in ("entity_id", "name", "qualified_name", "file_path")
                )
            ]

        calls, external_calls, ambiguous_calls = _resolve_calls(
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
            await run_transaction(
                MERGE_REPOSITORY_TOKENS_QUERY,
                extra_parameters={
                    "total_tokens": total_repo_tokens,
                    "tokenizer_model": DEFAULT_TOKEN_MODEL,
                },
            )

        if not replace_existing and affected_paths:
            if deleted_paths:
                await run_transaction(
                    DELETE_FILES_QUERY,
                    extra_parameters={"paths": deleted_paths},
                )
            await run_transaction(
                DELETE_STALE_FUNCTIONS_QUERY,
                extra_parameters={
                    "paths": affected_paths,
                    "entity_ids": [
                        function["entity_id"] for function in functions
                    ],
                },
            )
            await run_transaction(
                DELETE_OUTGOING_CALLS_QUERY,
                extra_parameters={"paths": changed_paths},
            )

        yield DatabaseWriteProgress("Pass 1: Creating Files...", 86)
        for batch in chunk_data(files, batch_size):
            await run_transaction(MERGE_FILES_QUERY, batch)

        yield DatabaseWriteProgress(
            "Pass 2: Embedding and Creating Functions...",
            90,
        )
        stage_started = perf_counter()
        function_count = 0
        async with aclosing(_embedded_function_batches(functions)) as embedded_batches:
            async for embedded_group in embedded_batches:
                for embedded_batch in chunk_data(embedded_group, batch_size):
                    await run_transaction(
                        MERGE_FUNCTIONS_QUERY,
                        [
                            {
                                **function,
                                "ambiguous_calls": ambiguous_calls.get(
                                    function["entity_id"], []
                                ),
                            }
                            for function in embedded_batch
                        ],
                    )
                    function_count += len(embedded_batch)
                    yield DatabaseWriteProgress(
                        f"Pass 2: Embedding and Creating Functions ({function_count}/{len(functions)})...",
                        90 + 3 * function_count // len(functions),
                    )
        logger.info(
            "Ingestion %s: embedded and stored functions in %.2fs",
            repo_name, perf_counter() - stage_started,
        )

        yield DatabaseWriteProgress("Pass 3: Mapping Dependencies...", 94)
        stage_started = perf_counter()
        call_count = 0
        total_calls = len(calls) + len(external_calls)
        for query, records in (
            (MERGE_CALLS_QUERY, calls),
            (MERGE_EXTERNAL_CALLS_QUERY, external_calls),
        ):
            for batch in chunk_data(records, batch_size):
                await run_transaction(query, batch)
                call_count += len(batch)
                yield DatabaseWriteProgress(
                    f"Pass 3: Mapping Dependencies ({call_count}/{total_calls})...",
                    94 + 2 * call_count // total_calls,
                )
        logger.info(
            "Ingestion %s: stored dependencies in %.2fs",
            repo_name, perf_counter() - stage_started,
        )

        if not replace_existing and affected_paths:
            await run_transaction(DELETE_ORPHAN_EXTERNAL_FUNCTIONS_QUERY)

    yield DatabaseWriteProgress(
        "Detecting architectural communities...",
        97,
    )
    stage_started = perf_counter()
    await run_leiden_clustering(repo_name)
    logger.info(
        "Ingestion %s: clustered graph in %.2fs",
        repo_name, perf_counter() - stage_started,
    )
    yield DatabaseWriteProgress(
        "Labeling architectural communities...",
        98,
    )
    stage_started = perf_counter()
    await label_and_store_communities(repo_name)
    logger.info(
        "Ingestion %s: labeled communities in %.2fs",
        repo_name, perf_counter() - stage_started,
    )
    yield DatabaseWriteProgress("Completing transaction...", 99)


async def save_parsed_ast_to_neo4j(
    parsed_files: list[IdentifiedFile],
    repo_name: str,
    replace_existing: bool = False,
    total_repo_tokens: int | None = None,
    deleted_file_paths: list[str] | None = None,
) -> None:
    """Persist identified files while discarding optional progress updates."""

    async for _ in save_parsed_ast_to_neo4j_with_progress(
        parsed_files,
        repo_name,
        replace_existing=replace_existing,
        total_repo_tokens=total_repo_tokens,
        deleted_file_paths=deleted_file_paths,
    ):
        pass


async def delete_repository_graph(repo_name: str) -> None:
    """Delete every graph node scoped to one canonical repository name."""

    async def delete(transaction: Any) -> None:
        result = await transaction.run(
            DELETE_REPOSITORY_QUERY,
            repo_name=repo_name,
        )
        await result.consume()

    async with get_neo4j_driver().session() as session:
        await session.execute_write(delete)


async def delete_all_repository_graphs() -> None:
    """Delete repository-scoped nodes left behind by prior app sessions."""

    async def delete(transaction: Any) -> None:
        result = await transaction.run(DELETE_ALL_REPOSITORY_GRAPHS_QUERY)
        await result.consume()

    async with get_neo4j_driver().session() as session:
        await session.execute_write(delete)
