"""Repository-scoped reads and writes of labeled architectural communities."""

from typing import Any

from app.database.driver import get_neo4j_driver


FETCH_COMMUNITIES_QUERY = """
MATCH (f:Function {repo_name: $repo_name})
WHERE f.leiden_community IS NOT NULL
WITH f.leiden_community AS comm_id,
     count(f) AS function_count,
     collect(coalesce(f.qualified_name, f.name))[..15] AS func_names,
     collect(DISTINCT f.file_path)[..5] AS file_paths
RETURN comm_id, function_count, func_names, file_paths
ORDER BY comm_id
"""

UNGROUP_SMALL_COMMUNITIES_QUERY = """
MATCH (f:Function {repo_name: $repo_name})
WHERE f.leiden_community IN $community_ids
SET f.leiden_community = $ungrouped_id
"""

DELETE_COMMUNITIES_QUERY = """
MATCH (c:Community {repo_name: $repo_name})
DETACH DELETE c
"""

STORE_COMMUNITIES_QUERY = """
UNWIND $communities AS comm
MERGE (c:Community {repo_name: $repo_name, community_id: comm.id})
SET c.name = comm.name,
    c.description = comm.description
WITH c, comm
MATCH (f:Function {
    repo_name: $repo_name,
    leiden_community: comm.id
})
MERGE (f)-[:IN_COMMUNITY]->(c)
"""


async def fetch_community_samples(repo_name: str) -> list[dict[str, Any]]:
    """Return each detected community's size and sample names and paths."""

    async with get_neo4j_driver().session() as session:
        result = await session.run(
            FETCH_COMMUNITIES_QUERY,
            repo_name=repo_name,
        )
        return await result.data()


async def replace_communities(
    repo_name: str,
    communities: list[dict[str, Any]],
    ungrouped_community_ids: list[int],
    ungrouped_id: int,
) -> None:
    """Atomically replace one repository's Community nodes.

    Functions in ``ungrouped_community_ids`` are first moved to
    ``ungrouped_id``; each of ``communities`` (``id``, ``name`` and
    ``description``) is then stored and linked to its member functions.
    """

    async def replace(transaction: Any) -> None:
        deleted = await transaction.run(
            DELETE_COMMUNITIES_QUERY,
            repo_name=repo_name,
        )
        await deleted.consume()
        if ungrouped_community_ids:
            ungrouped = await transaction.run(
                UNGROUP_SMALL_COMMUNITIES_QUERY,
                repo_name=repo_name,
                community_ids=ungrouped_community_ids,
                ungrouped_id=ungrouped_id,
            )
            await ungrouped.consume()
        if communities:
            stored = await transaction.run(
                STORE_COMMUNITIES_QUERY,
                repo_name=repo_name,
                communities=communities,
            )
            await stored.consume()

    async with get_neo4j_driver().session() as session:
        await session.execute_write(replace)
