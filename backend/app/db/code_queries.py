"""Repository-scoped reads that answer questions about a code graph.

Every function takes the repository it reads, so a caller that binds the
repository once (as the agent's tools do) cannot read another one's graph.
"""

from typing import Any

from app.db.driver import get_neo4j_driver
from app.utils.embeddings import FUNCTION_EMBEDDING_INDEX


# Function names are not unique, so name lookups may match several
# definitions; each result row identifies the definition it came from.
CALLERS_QUERY = """
MATCH (caller:Function {repo_name: $repo_name})-[:CALLS]->(target)
WHERE target.repo_name = $repo_name
  AND (target:Function OR target:ExternalFunction)
  AND (target.name = $func_name OR target.qualified_name = $func_name)
RETURN coalesce(caller.qualified_name, caller.name) AS caller,
       collect(DISTINCT caller.file_path) AS file_paths,
       coalesce(target.qualified_name, target.name) AS target,
       target.file_path AS target_file,
       coalesce(target.is_external, false) AS target_is_external
ORDER BY caller, target_file
LIMIT 100
"""

CODEBASE_STRUCTURE_QUERY = """
MATCH (f:File {repo_name: $repo_name})
RETURN f.path AS file_path
ORDER BY f.path
"""

FUNCTIONS_IN_FILE_QUERY = """
MATCH (f:File {path: $file_path, repo_name: $repo_name})-[:DEFINES]->
      (fn:Function)
RETURN coalesce(fn.qualified_name, fn.name) AS function_name
ORDER BY fn.start_line, function_name
"""

OUTGOING_DEPENDENCIES_QUERY = """
MATCH (caller:Function {repo_name: $repo_name})-[:CALLS]->(target)
WHERE caller.name = $func_name OR caller.qualified_name = $func_name
RETURN coalesce(caller.qualified_name, caller.name) AS caller_name,
       caller.file_path AS caller_file,
       coalesce(target.qualified_name, target.name) AS target_name,
       target.file_path AS target_file,
       coalesce(target.is_external, false) AS is_external
ORDER BY caller_file, caller_name, target_name, target_file
"""

EXTERNAL_DEPENDENCIES_QUERY = """
MATCH (fn:ExternalFunction {repo_name: $repo_name})
RETURN fn.name AS function_name
ORDER BY fn.name
"""

SEMANTIC_CODE_SEARCH_QUERY = f"""
MATCH (node:Function)
  SEARCH node IN (
    VECTOR INDEX {FUNCTION_EMBEDDING_INDEX}
    FOR $query_vector
    LIMIT $top_k
  ) SCORE AS score
WHERE node.repo_name = $repo_name
RETURN coalesce(node.qualified_name, node.name) AS function_name,
       node.file_path AS file_path,
       score
ORDER BY score DESC
"""

ARCHITECTURAL_SUBSYSTEMS_QUERY = """
MATCH (c:Community {repo_name: $repo_name})
OPTIONAL MATCH (f:Function {repo_name: $repo_name})-[:IN_COMMUNITY]->(c)
RETURN c.community_id AS id,
       c.name AS module_title,
       c.description AS module_description,
       count(f) AS function_count
ORDER BY function_count DESC
"""

REPOSITORY_TOKEN_QUERY = """
MATCH (repository:Repository {repo_name: $repo_name})
RETURN coalesce(repository.total_tokens, 0) AS total_tokens
LIMIT 1
"""


async def _read_records(query: str, **parameters: Any) -> list[dict[str, Any]]:
    """Run one read query in a fresh session and return its records."""

    async with get_neo4j_driver().session() as session:
        result = await session.run(query, **parameters)
        return await result.data()


async def fetch_callers(repo_name: str, function_name: str) -> list[dict[str, Any]]:
    """Return the direct callers of every definition with this name."""

    return await _read_records(
        CALLERS_QUERY,
        repo_name=repo_name,
        func_name=function_name,
    )


async def fetch_file_paths(repo_name: str) -> list[dict[str, Any]]:
    """Return every stored source file path, sorted."""

    return await _read_records(CODEBASE_STRUCTURE_QUERY, repo_name=repo_name)


async def fetch_functions_in_file(
    repo_name: str,
    file_path: str,
) -> list[dict[str, Any]]:
    """Return the functions one file defines, in source order."""

    return await _read_records(
        FUNCTIONS_IN_FILE_QUERY,
        repo_name=repo_name,
        file_path=file_path,
    )


async def fetch_outgoing_dependencies(
    repo_name: str,
    function_name: str,
) -> list[dict[str, Any]]:
    """Return what every definition with this name calls."""

    return await _read_records(
        OUTGOING_DEPENDENCIES_QUERY,
        repo_name=repo_name,
        func_name=function_name,
    )


async def fetch_external_functions(repo_name: str) -> list[dict[str, Any]]:
    """Return the called functions that are not defined in the repository."""

    return await _read_records(EXTERNAL_DEPENDENCIES_QUERY, repo_name=repo_name)


async def search_functions_by_embedding(
    repo_name: str,
    query_vector: list[float],
    top_k: int,
) -> list[dict[str, Any]]:
    """Return the functions nearest to ``query_vector``, best match first."""

    return await _read_records(
        SEMANTIC_CODE_SEARCH_QUERY,
        repo_name=repo_name,
        query_vector=query_vector,
        top_k=top_k,
    )


async def fetch_architectural_subsystems(repo_name: str) -> list[dict[str, Any]]:
    """Return the labeled communities, largest first."""

    return await _read_records(ARCHITECTURAL_SUBSYSTEMS_QUERY, repo_name=repo_name)


async def fetch_repository_total_tokens(repo_name: str) -> int:
    """Return the stored full-source token count for one repository."""

    async with get_neo4j_driver().session() as session:
        result = await session.run(
            REPOSITORY_TOKEN_QUERY,
            repo_name=repo_name,
        )
        record = await result.single()
    if record is None:
        return 0
    total_tokens = record["total_tokens"]
    return total_tokens if isinstance(total_tokens, int) else int(total_tokens)
