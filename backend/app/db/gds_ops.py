"""Repository-scoped Neo4j Graph Data Science operations."""

from typing import Any

from app.db import get_neo4j_driver


PROJECT_CODEBASE_GRAPH_QUERY = """
CALL gds.graph.project.cypher(
  $graph_name,
  'MATCH (n:Function {repo_name: $repo_name}) RETURN id(n) AS id',
  'MATCH (s:Function {repo_name: $repo_name})-[:CALLS]->(t:Function {repo_name: $repo_name}) RETURN id(s) AS source, id(t) AS target',
  {parameters: {repo_name: $repo_name}}
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount
"""

RUN_LEIDEN_QUERY = """
CALL gds.leiden.write(
  $graph_name,
  {
    writeProperty: 'leiden_community',
    relationshipWeightProperty: null
  }
)
YIELD communityCount, modularity
RETURN communityCount, modularity
"""

DROP_CODEBASE_GRAPH_QUERY = """
CALL gds.graph.drop($graph_name)
YIELD graphName
RETURN graphName
"""


async def run_leiden_clustering(repo_name: str) -> dict[str, Any]:
    """Write Leiden community IDs for one repository's function-call graph."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        raise ValueError("repo_name must not be blank")

    graph_name = f"codebase_graph_{normalized_repo_name}"
    async with get_neo4j_driver().session() as session:
        projection = await session.run(
            PROJECT_CODEBASE_GRAPH_QUERY,
            graph_name=graph_name,
            repo_name=normalized_repo_name,
        )
        await projection.consume()

        try:
            result = await session.run(
                RUN_LEIDEN_QUERY,
                graph_name=graph_name,
            )
            records = await result.data()
            return records[0] if records else {
                "communityCount": 0,
                "modularity": 0.0,
            }
        finally:
            dropped = await session.run(
                DROP_CODEBASE_GRAPH_QUERY,
                graph_name=graph_name,
            )
            await dropped.consume()
