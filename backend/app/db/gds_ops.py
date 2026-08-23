"""Repository-scoped Neo4j Graph Data Science operations."""

import logging
from typing import Any

from app.db import get_neo4j_driver


logger = logging.getLogger(__name__)


COUNT_REPOSITORY_FUNCTIONS_QUERY = """
MATCH (f:Function {repo_name: $repo_name})
RETURN count(f) AS node_count
"""

PROJECT_CODEBASE_GRAPH_QUERY = """
MATCH (s:Function {repo_name: $repo_name})
OPTIONAL MATCH (s)-[r:CALLS]->(t:Function {repo_name: $repo_name})
WITH gds.graph.project(
  $graph_name,
  s,
  t,
  {
    sourceNodeLabels: labels(s),
    targetNodeLabels: labels(t),
    relationshipType: type(r)
  },
  {undirectedRelationshipTypes: ['*']}
) AS g
RETURN
  g.graphName AS graphName,
  g.nodeCount AS nodeCount,
  g.relationshipCount AS relationshipCount
"""

RUN_LEIDEN_QUERY = """
CALL gds.leiden.write(
  $graph_name,
  {writeProperty: 'leiden_community'}
)
YIELD communityCount, modularity
RETURN communityCount, modularity
"""

DROP_CODEBASE_GRAPH_QUERY = """
CALL gds.graph.drop($graph_name, false)
YIELD graphName
RETURN graphName
"""


async def run_leiden_clustering(repo_name: str) -> dict[str, Any]:
    """Write Leiden community IDs for one repository's function-call graph."""

    normalized_repo_name = repo_name.strip()
    if not normalized_repo_name:
        raise ValueError("repo_name must not be blank")

    async with get_neo4j_driver().session() as session:
        count_result = await session.run(
            COUNT_REPOSITORY_FUNCTIONS_QUERY,
            repo_name=normalized_repo_name,
        )
        count_records = await count_result.data()
        node_count = count_records[0]["node_count"] if count_records else 0
        if node_count == 0:
            logger.warning(
                "Skipping clustering for %s: 0 nodes found",
                normalized_repo_name,
            )
            return {"communityCount": 0, "modularity": 0.0}

        graph_name = f"codebase_graph_{normalized_repo_name}"
        try:
            projection = await session.run(
                PROJECT_CODEBASE_GRAPH_QUERY,
                graph_name=graph_name,
                repo_name=normalized_repo_name,
            )
            await projection.consume()

            result = await session.run(
                RUN_LEIDEN_QUERY,
                graph_name=graph_name,
            )
            records = await result.data()
            summary = records[0] if records else {
                "communityCount": 0,
                "modularity": 0.0,
            }
            logger.info(
                "Leiden clustering completed for %s: communityCount=%s, modularity=%s",
                normalized_repo_name,
                summary["communityCount"],
                summary["modularity"],
            )
            return summary
        finally:
            dropped = await session.run(
                DROP_CODEBASE_GRAPH_QUERY,
                graph_name=graph_name,
            )
            await dropped.consume()
            logger.info("Released GDS projection %s", graph_name)
