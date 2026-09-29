"""Neo4j persistence operations for parsed source-code relationships."""

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any, TypeVar

from app.db import get_neo4j_driver
from app.db.call_resolution import call_site_id, resolve_call
from app.db.gds_ops import run_leiden_clustering
from app.services.community_summarizer import label_and_store_communities
from app.services.embedding_service import generate_embeddings
from app.utils.entity_identity import (
    generate_function_entity_id,
    normalize_repository_path,
)
from app.utils.tokens import DEFAULT_TOKEN_MODEL


DEFAULT_BATCH_SIZE = 100
BatchItem = TypeVar("BatchItem")

DELETE_REPOSITORY_QUERY = """
MATCH (node {repo_name: $repo_name})
DETACH DELETE node
"""

DELETE_REPOSITORY_GRAPH_QUERY = """
MATCH (n {repo_name: $repo_name})
DETACH DELETE n
"""

DELETE_ALL_REPOSITORY_GRAPHS_QUERY = """
MATCH (n)
WHERE n.repo_name IS NOT NULL
DETACH DELETE n
"""

CHECK_REPOSITORY_STATE_QUERY = """
OPTIONAL MATCH (repository:Repository {repo_name: $repo_name})
OPTIONAL MATCH (fn:Function {repo_name: $repo_name})
RETURN repository.graph_state AS graph_state,
       count(fn) AS function_count,
       count(CASE WHEN fn.entity_id IS NULL THEN 1 END) AS legacy_count
"""

MARK_REPOSITORY_BUILDING_QUERY = """
MERGE (repository:Repository {repo_name: $repo_name})
SET repository.name = $repo_name,
    repository.graph_state = 'building'
"""

MARK_REPOSITORY_READY_QUERY = """
MATCH (repository:Repository {repo_name: $repo_name})
SET repository.graph_state = 'ready',
    repository.graph_updated_at = datetime()
"""

DELETE_FILE_FUNCTIONS_QUERY = """
MATCH (fn:Function {repo_name: $repo_name})
WHERE fn.file_path IN $paths
DETACH DELETE fn
"""

DELETE_FILE_CALLS_QUERY = """
MATCH (call:UnresolvedCall {repo_name: $repo_name})
WHERE call.file_path IN $paths
DETACH DELETE call
"""

DELETE_FILES_QUERY = """
MATCH (file:File {repo_name: $repo_name})
WHERE file.path IN $paths
DETACH DELETE file
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
MERGE (fn:Function {repo_name: $repo_name, entity_id: func.entity_id})
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
    fn.has_body = func.has_body,
    fn.raw_code = func.raw_code,
    fn.embedding = func.embedding,
    fn.external = false,
    fn.is_external = false
MERGE (f)-[:DEFINES]->(fn)
"""

MERGE_CALLS_QUERY = """
UNWIND $batch AS call
MATCH (caller:Function {repo_name: $repo_name, entity_id: call.caller_id})
MATCH (target:Function {repo_name: $repo_name, entity_id: call.target_id})
MERGE (caller)-[relationship:CALLS {call_id: call.call_id}]->(target)
SET relationship.resolution_status = call.resolution_status,
    relationship.provenance = call.provenance,
    relationship.inferred_from_file_scope = false,
    relationship.source_file = call.file_path,
    relationship.target_name = call.name,
    relationship.syntax = call.syntax,
    relationship.start_line = call.start_line,
    relationship.end_line = call.end_line,
    relationship.start_column = call.start_column,
    relationship.end_column = call.end_column
"""

MERGE_UNRESOLVED_CALLS_QUERY = """
UNWIND $batch AS call
MERGE (unresolved:UnresolvedCall:ExternalFunction {
    repo_name: $repo_name, call_id: call.call_id
})
SET unresolved.name = call.name,
    unresolved.syntax = call.syntax,
    unresolved.file_path = call.file_path,
    unresolved.caller_entity_id = call.caller_id,
    unresolved.start_line = call.start_line,
    unresolved.end_line = call.end_line,
    unresolved.start_column = call.start_column,
    unresolved.end_column = call.end_column,
    unresolved.resolution_status = call.resolution_status,
    unresolved.provenance = call.provenance,
    unresolved.external = true,
    unresolved.is_external = true,
    unresolved.nodeType = 'UnresolvedCall'
WITH unresolved, call
MATCH (source {repo_name: $repo_name})
WHERE (source:Function AND source.entity_id = call.caller_id)
   OR (source:File AND call.caller_id IS NULL AND source.path = call.file_path)
MERGE (source)-[:HAS_UNRESOLVED_CALL]->(unresolved)
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


def _extract_etl_records(
    parsed_data_list: list[dict[str, Any]],
    repo_name: str,
) -> tuple[
    list[dict[str, str]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Validate parsed identities and resolve only supported call-site evidence."""

    files: dict[str, dict[str, str]] = {}
    functions: dict[str, dict[str, Any]] = {}
    call_sites: list[tuple[dict[str, Any] | None, str, dict[str, Any]]] = []
    for parsed_file in parsed_data_list:
        file_path = normalize_repository_path(parsed_file["file_path"])
        if parsed_file.get("repository", repo_name) != repo_name:
            raise ValueError("parsed file belongs to a different repository")
        files[file_path] = {"path": file_path}
        parsed_functions = parsed_file.get("functions")
        if not isinstance(parsed_functions, list):
            raise ValueError("parsed file has no structured function records")
        for function in parsed_functions:
            if not isinstance(function, dict):
                raise ValueError("function record must be a dictionary")
            if normalize_repository_path(function["file_path"]) != file_path:
                raise ValueError("function path does not match defining file")
            if function.get("repository", repo_name) != repo_name:
                raise ValueError("function belongs to a different repository")
            expected_id = generate_function_entity_id(
                repo_name,
                file_path,
                function["language"],
                function["qualified_name"],
                function["definition_discriminator"],
            )
            if function.get("entity_id") != expected_id:
                raise ValueError("function is missing its canonical CG-002A entity_id")
            entity = {
                key: function[key]
                for key in (
                    "entity_id", "name", "qualified_name", "language",
                    "definition_discriminator", "start_line", "end_line",
                    "start_column", "end_column", "raw_code", "has_body",
                )
            }
            entity["file_path"] = file_path
            entity["signature"] = function.get("signature")
            prior = functions.get(expected_id)
            if prior is not None and prior != entity:
                raise ValueError("conflicting definitions share one entity_id")
            functions[expected_id] = entity
            for call in function.get("calls", []):
                call_sites.append((entity, file_path, call))
        for call in parsed_file.get("unattributed_calls", []):
            call_sites.append((None, file_path, call))

    all_functions = list(functions.values())
    resolved: dict[str, dict[str, Any]] = {}
    unresolved: dict[str, dict[str, Any]] = {}
    for caller, file_path, call in call_sites:
        if not isinstance(call, dict) or not isinstance(call.get("name"), str):
            raise ValueError("call site is missing its syntactic name")
        caller_id = caller["entity_id"] if caller is not None else None
        call_id = call_site_id(file_path, caller_id, call)
        target_id, status, provenance = resolve_call(caller, call, all_functions)
        record = {
            "call_id": call_id,
            "caller_id": caller_id,
            "target_id": target_id,
            "file_path": file_path,
            "name": call["name"],
            "syntax": call["syntax"],
            "start_line": call["start_line"],
            "end_line": call["end_line"],
            "start_column": call["start_column"],
            "end_column": call["end_column"],
            "resolution_status": status,
            "provenance": provenance,
        }
        bucket = resolved if target_id is not None else unresolved
        prior = bucket.get(call_id)
        if prior is not None and prior != record:
            raise ValueError("conflicting call sites share one call_id")
        bucket[call_id] = record
    return list(files.values()), all_functions, list(resolved.values()), list(unresolved.values())


def _function_embedding_text(function: dict[str, Any]) -> str:
    """Build stable semantic context from currently available AST fields."""

    return (
        f"Function: {function['qualified_name']}\n"
        f"File: {function['file_path']}"
    )


def _resolve_total_repo_tokens(
    parsed_data_list: list[dict[str, Any]],
    total_repo_tokens: int | None,
) -> int | None:
    """Resolve an explicit full-repository total or parsed-file totals."""

    if total_repo_tokens is not None:
        if total_repo_tokens < 0:
            raise ValueError("total_repo_tokens must not be negative")
        return total_repo_tokens

    parsed_token_counts = [
        value
        for parsed_file in parsed_data_list
        if isinstance((value := parsed_file.get("source_tokens")), int)
        and not isinstance(value, bool)
        and value >= 0
    ]
    return sum(parsed_token_counts) if parsed_token_counts else None


async def save_parsed_ast_to_neo4j_with_progress(
    parsed_data_list: list[dict[str, Any]],
    repo_name: str,
    replace_existing: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    total_repo_tokens: int | None = None,
    deleted_file_paths: list[str] | None = None,
) -> AsyncIterator[DatabaseWriteProgress]:
    """Persist one repository while hiding builds until they are complete."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        raise ValueError("repo_name must not be blank")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    files, functions, calls, unresolved_calls = _extract_etl_records(
        parsed_data_list, normalized_repo_name
    )
    deleted_paths = {
        normalize_repository_path(path)
        for path in (deleted_file_paths or [])
    }
    changed_paths = {file["path"] for file in files}
    if changed_paths & deleted_paths:
        raise ValueError("a file cannot be updated and deleted in one ingestion")
    if not replace_existing and not (changed_paths or deleted_paths):
        raise ValueError("incremental ingestion has no affected files")
    # Changed-file token counts are not a new repository-wide baseline.
    resolved_total_tokens = (
        _resolve_total_repo_tokens(parsed_data_list, total_repo_tokens)
        if replace_existing or total_repo_tokens is not None
        else None
    )

    async with get_neo4j_driver().session() as session:
        async def run_transaction(
            query: str,
            batch: list[dict[str, Any]] | None = None,
            extra_parameters: dict[str, Any] | None = None,
        ) -> None:
            async def execute(transaction: Any) -> None:
                parameters: dict[str, Any] = {
                    "repo_name": normalized_repo_name
                }
                if batch is not None:
                    parameters["batch"] = batch
                if extra_parameters is not None:
                    parameters.update(extra_parameters)
                result = await transaction.run(query, **parameters)
                await result.consume()

            await session.execute_write(execute)

        if replace_existing:
            await run_transaction(DELETE_REPOSITORY_QUERY)
        else:
            status_result = await session.run(
                CHECK_REPOSITORY_STATE_QUERY, repo_name=normalized_repo_name
            )
            status_record = await status_result.single()
            if (
                status_record is None
                or status_record["graph_state"] != "ready"
                or status_record["legacy_count"] > 0
            ):
                raise ValueError(
                    "incremental ingestion requires a ready identity-based "
                    "repository graph; rebuild the repository first"
                )
        await run_transaction(MARK_REPOSITORY_BUILDING_QUERY)
        if not replace_existing:
            affected_paths = sorted(changed_paths | deleted_paths)
            parameters = {"paths": affected_paths}
            for query in (
                DELETE_FILE_FUNCTIONS_QUERY,
                DELETE_FILE_CALLS_QUERY,
                DELETE_FILES_QUERY,
            ):
                await run_transaction(query, extra_parameters=parameters)

        if resolved_total_tokens is not None:
            await run_transaction(
                MERGE_REPOSITORY_TOKENS_QUERY,
                extra_parameters={
                    "total_tokens": resolved_total_tokens,
                    "tokenizer_model": DEFAULT_TOKEN_MODEL,
                },
            )

        yield DatabaseWriteProgress("Pass 1: Creating Files...", 86)
        for batch in chunk_data(files, batch_size):
            await run_transaction(MERGE_FILES_QUERY, batch)

        yield DatabaseWriteProgress(
            "Pass 2: Embedding and Creating Functions...",
            90,
        )
        for batch in chunk_data(functions, batch_size):
            embeddings = await generate_embeddings(
                [_function_embedding_text(function) for function in batch]
            )
            embedded_batch = [
                {**function, "embedding": embedding}
                for function, embedding in zip(batch, embeddings, strict=True)
            ]
            await run_transaction(MERGE_FUNCTIONS_QUERY, embedded_batch)

        yield DatabaseWriteProgress("Pass 3: Mapping Dependencies...", 94)
        for batch in chunk_data(calls, batch_size):
            await run_transaction(MERGE_CALLS_QUERY, batch)
        for batch in chunk_data(unresolved_calls, batch_size):
            await run_transaction(MERGE_UNRESOLVED_CALLS_QUERY, batch)

    yield DatabaseWriteProgress(
        "Detecting architectural communities...",
        97,
    )
    await run_leiden_clustering(normalized_repo_name)
    yield DatabaseWriteProgress(
        "Labeling architectural communities...",
        98,
    )
    await label_and_store_communities(normalized_repo_name)
    async with get_neo4j_driver().session() as session:
        result = await session.run(
            MARK_REPOSITORY_READY_QUERY,
            repo_name=normalized_repo_name,
        )
        await result.consume()
    yield DatabaseWriteProgress("Completing transaction...", 99)


async def save_parsed_ast_to_neo4j(
    parsed_data_list: list[dict[str, Any]],
    repo_name: str,
    replace_existing: bool = False,
    total_repo_tokens: int | None = None,
    deleted_file_paths: list[str] | None = None,
) -> None:
    """Persist parsed AST data while discarding optional progress updates."""

    async for _ in save_parsed_ast_to_neo4j_with_progress(
        parsed_data_list,
        repo_name,
        replace_existing=replace_existing,
        total_repo_tokens=total_repo_tokens,
        deleted_file_paths=deleted_file_paths,
    ):
        pass


async def delete_repository_graph(repo_name: str) -> None:
    """Delete every graph node scoped to one canonical repository name."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        raise ValueError("repo_name must not be blank")

    async def delete(transaction: Any) -> None:
        result = await transaction.run(
            DELETE_REPOSITORY_GRAPH_QUERY,
            repo_name=normalized_repo_name,
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
