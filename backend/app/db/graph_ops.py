"""Neo4j persistence operations for parsed source-code relationships."""

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any, TypeVar

from app.db import get_neo4j_driver


DEFAULT_BATCH_SIZE = 100
BatchItem = TypeVar("BatchItem")

DELETE_REPOSITORY_QUERY = """
MATCH (node)
WHERE (node:File OR node:Function) AND node.repo_name = $repo_name
DETACH DELETE node
"""

DELETE_REPOSITORY_GRAPH_QUERY = """
MATCH (n {repo_name: $repo_name})
DETACH DELETE n
"""

MERGE_FILES_QUERY = """
UNWIND $batch AS file
MERGE (f:File {path: file.path, repo_name: $repo_name})
SET f.updated_at = datetime()
"""

MERGE_FUNCTIONS_QUERY = """
UNWIND $batch AS func
MATCH (f:File {path: func.file_path, repo_name: $repo_name})
MERGE (fn:Function {name: func.name, repo_name: $repo_name})
REMOVE fn:ExternalFunction
SET fn.file = coalesce(fn.file, func.file_path),
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

        defined_functions = _string_list(
            parsed_file.get("defined_functions")
        )
        outgoing_calls = _string_list(parsed_file.get("outgoing_calls"))
        for function_name in defined_functions:
            function_key = (file_path, function_name)
            if function_key not in seen_functions:
                seen_functions.add(function_key)
                functions.append(
                    {"name": function_name, "file_path": file_path}
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


async def save_parsed_ast_to_neo4j_with_progress(
    parsed_data_list: list[dict[str, Any]],
    repo_name: str,
    replace_existing: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> AsyncIterator[DatabaseWriteProgress]:
    """Persist one repository through bounded file, function, and call passes."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        raise ValueError("repo_name must not be blank")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    files, functions, calls = _extract_etl_records(parsed_data_list)

    async with get_neo4j_driver().session() as session:
        async def run_transaction(
            query: str,
            batch: list[dict[str, str]] | None = None,
        ) -> None:
            async def execute(transaction: Any) -> None:
                parameters: dict[str, Any] = {
                    "repo_name": normalized_repo_name
                }
                if batch is not None:
                    parameters["batch"] = batch
                result = await transaction.run(query, **parameters)
                await result.consume()

            await session.execute_write(execute)

        if replace_existing:
            await run_transaction(DELETE_REPOSITORY_QUERY)

        yield DatabaseWriteProgress("Pass 1: Creating Files...", 86)
        for batch in chunk_data(files, batch_size):
            await run_transaction(MERGE_FILES_QUERY, batch)

        yield DatabaseWriteProgress("Pass 2: Creating Functions...", 90)
        for batch in chunk_data(functions, batch_size):
            await run_transaction(MERGE_FUNCTIONS_QUERY, batch)

        yield DatabaseWriteProgress("Pass 3: Mapping Dependencies...", 94)
        for batch in chunk_data(calls, batch_size):
            await run_transaction(MERGE_CALLS_QUERY, batch)

        await run_transaction(TAG_EXTERNAL_FUNCTIONS_QUERY)
        yield DatabaseWriteProgress("Completing transaction...", 98)


async def save_parsed_ast_to_neo4j(
    parsed_data_list: list[dict[str, Any]],
    repo_name: str,
    replace_existing: bool = False,
) -> None:
    """Persist parsed AST data while discarding optional progress updates."""

    async for _ in save_parsed_ast_to_neo4j_with_progress(
        parsed_data_list,
        repo_name,
        replace_existing=replace_existing,
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
