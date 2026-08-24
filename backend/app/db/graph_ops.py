"""Neo4j persistence operations for parsed source-code relationships."""

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any, TypeVar

from app.db import get_neo4j_driver
from app.db.gds_ops import run_leiden_clustering
from app.services.community_summarizer import label_and_store_communities
from app.services.embedding_service import generate_embeddings
from app.utils.tokens import DEFAULT_TOKEN_MODEL


DEFAULT_BATCH_SIZE = 100
BatchItem = TypeVar("BatchItem")

DELETE_REPOSITORY_QUERY = """
MATCH (node)
WHERE (node:Repository OR node:File OR node:Function OR node:Community)
  AND node.repo_name = $repo_name
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
MERGE (fn:Function {name: func.name, repo_name: $repo_name})
REMOVE fn:ExternalFunction
SET fn.file = coalesce(fn.file, func.file_path),
    fn.file_path = func.file_path,
    fn.raw_code = func.raw_code,
    fn.embedding = func.embedding,
    fn.external = false,
    fn.is_external = false
MERGE (f)-[:DEFINES]->(fn)
"""

MERGE_CALLS_QUERY = """
UNWIND $batch AS call
MATCH (caller:Function {
    name: call.caller_name,
    repo_name: $repo_name
})
MERGE (target:Function {
    name: call.target_name,
    repo_name: $repo_name
})
ON CREATE SET target.external = true
MERGE (caller)-[relationship:CALLS]->(target)
SET relationship.inferred_from_file_scope = true,
    relationship.source_files = CASE
        WHEN call.file_path IN coalesce(relationship.source_files, [])
        THEN coalesce(relationship.source_files, [])
        ELSE coalesce(relationship.source_files, []) + call.file_path
    END
"""

TAG_EXTERNAL_FUNCTIONS_QUERY = """
MATCH (fn:Function {repo_name: $repo_name})
WHERE NOT ()-[:DEFINES]->(fn)
SET fn:ExternalFunction, fn.is_external = true
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


def _string_list(value: object) -> list[str]:
    """Keep unique, non-empty strings from an untrusted parsed-data field."""

    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(item for item in value if isinstance(item, str) and item)
    )


def _extract_etl_records(
    parsed_data_list: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Flatten parsed AST data into file, function, and call records."""

    files: list[dict[str, str]] = []
    functions: list[dict[str, str]] = []
    calls: list[dict[str, str]] = []
    seen_files: set[str] = set()
    seen_functions: set[tuple[str, str]] = set()
    seen_calls: set[tuple[str, str, str]] = set()

    for parsed_file in parsed_data_list:
        file_path = parsed_file.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            continue
        if file_path not in seen_files:
            seen_files.add(file_path)
            files.append({"path": file_path})

        function_records: list[dict[str, str]] = []
        seen_function_names: set[str] = set()
        parsed_functions = parsed_file.get("functions")
        if isinstance(parsed_functions, list):
            for parsed_function in parsed_functions:
                if not isinstance(parsed_function, dict):
                    continue
                function_name = parsed_function.get("name")
                raw_code = parsed_function.get("raw_code")
                if (
                    not isinstance(function_name, str)
                    or not function_name
                    or function_name in seen_function_names
                ):
                    continue
                seen_function_names.add(function_name)
                function_records.append(
                    {
                        "name": function_name,
                        "raw_code": raw_code if isinstance(raw_code, str) else "",
                    }
                )
        for function_name in _string_list(
            parsed_file.get("defined_functions")
        ):
            if function_name in seen_function_names:
                continue
            seen_function_names.add(function_name)
            function_records.append({"name": function_name, "raw_code": ""})

        outgoing_calls = _string_list(parsed_file.get("outgoing_calls"))
        for function_record in function_records:
            function_name = function_record["name"]
            function_key = (file_path, function_name)
            if function_key not in seen_functions:
                seen_functions.add(function_key)
                functions.append(
                    {
                        "name": function_name,
                        "file_path": file_path,
                        "raw_code": function_record["raw_code"],
                    }
                )

            for target_name in outgoing_calls:
                call_key = (function_name, target_name, file_path)
                if call_key in seen_calls:
                    continue
                seen_calls.add(call_key)
                calls.append(
                    {
                        "caller_name": function_name,
                        "target_name": target_name,
                        "file_path": file_path,
                    }
                )

    return files, functions, calls


def _function_embedding_text(function: dict[str, str]) -> str:
    """Build stable semantic context from currently available AST fields."""

    return (
        f"Function: {function['name']}\n"
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
) -> AsyncIterator[DatabaseWriteProgress]:
    """Persist one repository through bounded file, function, and call passes."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        raise ValueError("repo_name must not be blank")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    files, functions, calls = _extract_etl_records(parsed_data_list)
    resolved_total_tokens = _resolve_total_repo_tokens(
        parsed_data_list,
        total_repo_tokens,
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

        await run_transaction(TAG_EXTERNAL_FUNCTIONS_QUERY)

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
    yield DatabaseWriteProgress("Completing transaction...", 99)


async def save_parsed_ast_to_neo4j(
    parsed_data_list: list[dict[str, Any]],
    repo_name: str,
    replace_existing: bool = False,
    total_repo_tokens: int | None = None,
) -> None:
    """Persist parsed AST data while discarding optional progress updates."""

    async for _ in save_parsed_ast_to_neo4j_with_progress(
        parsed_data_list,
        repo_name,
        replace_existing=replace_existing,
        total_repo_tokens=total_repo_tokens,
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
