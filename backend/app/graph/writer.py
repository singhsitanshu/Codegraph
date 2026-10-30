"""Neo4j persistence operations for parsed source-code relationships.

Functions are keyed by the deterministic CG-002A ``entity_id`` rather than by
their simple names, so same-named definitions in different files, classes, or
lexical scopes remain separate graph nodes. Callers pass ready records; this
module only runs repository-scoped queries.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from neo4j import AsyncSession

from app.database.driver import get_neo4j_driver


# Records written per transaction, so each Neo4j transaction stays small.
DEFAULT_BATCH_SIZE = 100

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


class RepositoryGraphWriter:
    """Repository-scoped graph writes that share one Neo4j session.

    Every method runs in its own transaction; batch methods write the records
    they are given in one transaction, so callers choose the batch size.
    """

    def __init__(self, session: AsyncSession, repo_name: str) -> None:
        self._session = session
        self._repo_name = repo_name

    async def _write(
        self,
        query: str,
        batch: list[dict[str, Any]] | None = None,
        **parameters: Any,
    ) -> None:
        async def execute(transaction: Any) -> None:
            arguments: dict[str, Any] = {"repo_name": self._repo_name}
            if batch is not None:
                arguments["batch"] = batch
            arguments.update(parameters)
            result = await transaction.run(query, **arguments)
            await result.consume()

        await self._session.execute_write(execute)

    async def delete_repository(self) -> None:
        """Remove every node of the repository, including communities."""

        await self._write(DELETE_REPOSITORY_QUERY)

    async def fetch_definitions_outside(
        self,
        paths: list[str],
    ) -> list[dict[str, str]]:
        """Return the identity fields of stored functions not in ``paths``."""

        result = await self._session.run(
            FETCH_EXISTING_DEFINITIONS_QUERY,
            repo_name=self._repo_name,
            paths=paths,
        )
        return [
            record
            for record in await result.data()
            if all(
                isinstance(record.get(key), str)
                for key in ("entity_id", "name", "qualified_name", "file_path")
            )
        ]

    async def store_token_baseline(
        self,
        total_tokens: int,
        tokenizer_model: str,
    ) -> None:
        """Record the full-source token count on the Repository node."""

        await self._write(
            MERGE_REPOSITORY_TOKENS_QUERY,
            total_tokens=total_tokens,
            tokenizer_model=tokenizer_model,
        )

    async def delete_files(self, paths: list[str]) -> None:
        """Remove File nodes for ``paths``."""

        await self._write(DELETE_FILES_QUERY, paths=paths)

    async def delete_stale_functions(
        self,
        paths: list[str],
        keep_entity_ids: list[str],
    ) -> None:
        """Remove functions in ``paths`` whose identity is not kept."""

        await self._write(
            DELETE_STALE_FUNCTIONS_QUERY,
            paths=paths,
            entity_ids=keep_entity_ids,
        )

    async def delete_outgoing_calls(self, paths: list[str]) -> None:
        """Remove CALLS edges leaving functions in ``paths``."""

        await self._write(DELETE_OUTGOING_CALLS_QUERY, paths=paths)

    async def write_files(self, batch: list[dict[str, Any]]) -> None:
        """Merge File records under the repository."""

        await self._write(MERGE_FILES_QUERY, batch)

    async def write_functions(self, batch: list[dict[str, Any]]) -> None:
        """Merge embedded Function records under their defining files."""

        await self._write(MERGE_FUNCTIONS_QUERY, batch)

    async def write_calls(self, batch: list[dict[str, Any]]) -> None:
        """Merge resolved Function-to-Function CALLS edges."""

        await self._write(MERGE_CALLS_QUERY, batch)

    async def write_external_calls(self, batch: list[dict[str, Any]]) -> None:
        """Merge CALLS edges to ExternalFunction nodes."""

        await self._write(MERGE_EXTERNAL_CALLS_QUERY, batch)

    async def delete_orphan_external_functions(self) -> None:
        """Remove ExternalFunction nodes that nothing calls any more."""

        await self._write(DELETE_ORPHAN_EXTERNAL_FUNCTIONS_QUERY)


@asynccontextmanager
async def open_repository_graph_writer(
    repo_name: str,
) -> AsyncIterator[RepositoryGraphWriter]:
    """Open one session for a sequence of writes to ``repo_name``'s graph."""

    async with get_neo4j_driver().session() as session:
        yield RepositoryGraphWriter(session, repo_name)


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
