"""Neo4j schema setup, run once by the application lifespan."""

import logging

from app.database.driver import get_neo4j_driver
from app.embeddings.constants import EMBEDDING_DIMENSIONS, FUNCTION_EMBEDDING_INDEX


logger = logging.getLogger(__name__)
DATABASE_INDEX_QUERIES = (
    # CG-002A entity IDs hash the repository name, so they are globally unique.
    "CREATE CONSTRAINT function_entity_id IF NOT EXISTS "
    "FOR (fn:Function) REQUIRE fn.entity_id IS UNIQUE",
    "CREATE INDEX repository_repo_name IF NOT EXISTS "
    "FOR (r:Repository) ON (r.repo_name)",
    "CREATE INDEX file_repo_path IF NOT EXISTS "
    "FOR (f:File) ON (f.repo_name, f.path)",
    "CREATE INDEX func_repo_name IF NOT EXISTS "
    "FOR (fn:Function) ON (fn.repo_name, fn.name)",
    "CREATE INDEX func_repo_file IF NOT EXISTS "
    "FOR (fn:Function) ON (fn.repo_name, fn.file_path)",
    "CREATE INDEX ext_func_repo_name IF NOT EXISTS "
    "FOR (ext:ExternalFunction) ON (ext.repo_name, ext.name)",
    "CREATE INDEX community_repo_id IF NOT EXISTS "
    "FOR (c:Community) ON (c.repo_name, c.community_id)",
    "CREATE INDEX func_repo_community IF NOT EXISTS "
    "FOR (fn:Function) ON (fn.repo_name, fn.leiden_community)",
    f"CREATE VECTOR INDEX `{FUNCTION_EMBEDDING_INDEX}` IF NOT EXISTS "
    "FOR (fn:Function) ON (fn.embedding) "
    "OPTIONS {indexConfig: {"
    f"`vector.dimensions`: {EMBEDDING_DIMENSIONS}, "
    "`vector.similarity_function`: 'cosine'"
    "}}",
)
AWAIT_INDEXES_QUERY = "CALL db.awaitIndexes(300)"


async def initialize_database() -> None:
    """Create and await the indexes required by repository-scoped merges.

    Every statement is idempotent, so a repeated startup leaves the schema as
    it is. An unreachable or misconfigured Neo4j raises here and fails startup.
    """

    async with get_neo4j_driver().session() as session:
        for query in (*DATABASE_INDEX_QUERIES, AWAIT_INDEXES_QUERY):
            result = await session.run(query)
            await result.consume()

    logger.info("Neo4j repository indexes are online")
