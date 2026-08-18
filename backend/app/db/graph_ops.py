"""Neo4j persistence operations for parsed source-code relationships."""

from typing import Any

from app.db import get_neo4j_driver


DELETE_REPOSITORY_QUERY = """
MATCH (node)
WHERE (node:File OR node:Function) AND node.repo_name = $repo_name
DETACH DELETE node
"""

TAG_EXTERNAL_FUNCTIONS_QUERY = """
MATCH (fn:Function {repo_name: $repo_name})
WHERE NOT ()-[:DEFINES]->(fn)
SET fn:ExternalFunction, fn.is_external = true
"""

MERGE_FILES_QUERY = """
UNWIND $items AS item
MERGE (file:File {path: item.file_path, repo_name: $repo_name})
SET file.updated_at = datetime()
"""

MERGE_FUNCTIONS_QUERY = """
UNWIND $items AS item
MATCH (file:File {path: item.file_path, repo_name: $repo_name})
UNWIND item.defined_functions AS function_name
MERGE (function:Function {
    name: function_name,
    file: item.file_path,
    repo_name: $repo_name
})
MERGE (file)-[:DEFINES]->(function)
"""

MERGE_LOCAL_CALLS_QUERY = """
UNWIND $items AS item
UNWIND item.defined_functions AS caller_name
MATCH (caller:Function {
    name: caller_name,
    file: item.file_path,
    repo_name: $repo_name
})
UNWIND item.outgoing_calls AS callee_name
WITH item, caller, callee_name
WHERE callee_name IN item.defined_functions
MATCH (callee:Function {
    name: callee_name,
    file: item.file_path,
    repo_name: $repo_name
})
MERGE (caller)-[call:CALLS]->(callee)
SET call.inferred_from_file_scope = true,
    call.source_files = CASE
        WHEN item.file_path IN coalesce(call.source_files, [])
        THEN coalesce(call.source_files, [])
        ELSE coalesce(call.source_files, []) + item.file_path
    END
"""

MERGE_EXTERNAL_CALLS_QUERY = """
UNWIND $items AS item
UNWIND item.defined_functions AS caller_name
MATCH (caller:Function {
    name: caller_name,
    file: item.file_path,
    repo_name: $repo_name
})
UNWIND item.outgoing_calls AS callee_name
WITH item, caller, callee_name
WHERE NOT callee_name IN item.defined_functions
MERGE (callee:Function {
    name: callee_name,
    external: true,
    repo_name: $repo_name
})
MERGE (caller)-[call:CALLS]->(callee)
SET call.inferred_from_file_scope = true,
    call.source_files = CASE
        WHEN item.file_path IN coalesce(call.source_files, [])
        THEN coalesce(call.source_files, [])
        ELSE coalesce(call.source_files, []) + item.file_path
    END
"""


def _string_list(value: object) -> list[str]:
    """Keep unique, non-empty strings from an untrusted parsed-data field."""

    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(item for item in value if isinstance(item, str) and item)
    )


def _normalize_parsed_data(
    parsed_data_list: list[dict[str, Any]],
) -> list[dict[str, str | list[str]]]:
    """Validate the parser payload shape before passing it to Cypher."""

    items: list[dict[str, str | list[str]]] = []
    for parsed_data in parsed_data_list:
        file_path = parsed_data.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            continue
        items.append(
            {
                "file_path": file_path,
                "defined_functions": _string_list(
                    parsed_data.get("defined_functions")
                ),
                "outgoing_calls": _string_list(parsed_data.get("outgoing_calls")),
            }
        )
    return items


async def save_parsed_ast_to_neo4j(
    parsed_data_list: list[dict[str, Any]],
    repo_name: str,
    replace_existing: bool = False,
) -> None:
    """Persist parsed files, functions, definitions, and calls using ``MERGE``.

    The current parser returns calls at file scope rather than attaching each
    call site to its enclosing function. Until caller-scoped extraction is
    available, every function defined in the file is conservatively connected
    to every outgoing call and the relationship is marked as inferred.

    Args:
        parsed_data_list: Results returned by ``parse_changed_files``.
        repo_name: Canonical ``owner/repository`` scope for every graph node.
        replace_existing: Delete this repository's existing scoped graph in the
            same transaction before writing a complete fresh parse.
    """

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        raise ValueError("repo_name must not be blank")

    items = _normalize_parsed_data(parsed_data_list)
    if not items:
        return

    async def persist(transaction: Any) -> None:
        if replace_existing:
            result = await transaction.run(
                DELETE_REPOSITORY_QUERY,
                repo_name=normalized_repo_name,
            )
            await result.consume()

        for query in (
            MERGE_FILES_QUERY,
            MERGE_FUNCTIONS_QUERY,
            MERGE_LOCAL_CALLS_QUERY,
            MERGE_EXTERNAL_CALLS_QUERY,
        ):
            result = await transaction.run(
                query,
                items=items,
                repo_name=normalized_repo_name,
            )
            await result.consume()

        result = await transaction.run(
            TAG_EXTERNAL_FUNCTIONS_QUERY,
            repo_name=normalized_repo_name,
        )
        await result.consume()

    async with get_neo4j_driver().session() as session:
        await session.execute_write(persist)
