"""Repository-scoped Neo4j Graph Data Science operations."""

import logging
from typing import Any

from app.db import get_neo4j_driver


logger = logging.getLogger(__name__)


COUNT_REPOSITORY_FUNCTIONS_QUERY = """
MATCH (f:Function {repo_name: $repo_name})
RETURN count(f) AS node_count
"""

# Resolved Function-to-Function calls alone leave most functions isolated
# (Leiden then gives each its own community), so the projection also links
# functions through the files that define them and the external callees they
# share. File and ExternalFunction nodes only provide structure; community IDs
# are written back to Function nodes.
PROJECT_CODEBASE_GRAPH_QUERY = """
CALL {
  MATCH (s:Function {repo_name: $repo_name})
  OPTIONAL MATCH (s)-[r:CALLS]->(t)
  WHERE t.repo_name = $repo_name AND (t:Function OR t:ExternalFunction)
  RETURN s, t, type(r) AS relationship_type
  UNION
  MATCH (s:File {repo_name: $repo_name})-[r:DEFINES]->
        (t:Function {repo_name: $repo_name})
  RETURN s, t, type(r) AS relationship_type
}
WITH gds.graph.project(
  $graph_name,
  s,
  t,
  {
    sourceNodeLabels: labels(s),
    targetNodeLabels: labels(t),
    relationshipType: relationship_type
  },
  {undirectedRelationshipTypes: ['*']}
) AS g
RETURN
  g.graphName AS graphName,
  g.nodeCount AS nodeCount,
  g.relationshipCount AS relationshipCount
"""

# Communities are mutated in memory, then the final community ID (not the
# intermediate levels) is written to Function nodes only and summarized.
RUN_LEIDEN_QUERY = """
CALL gds.leiden.mutate(
  $graph_name,
  {mutateProperty: 'leiden_community'}
)
YIELD modularity
CALL gds.graph.list($graph_name)
YIELD nodeCount, relationshipCount
CALL gds.graph.nodeProperty.stream(
  $graph_name,
  'leiden_community',
  ['Function']
)
YIELD nodeId, propertyValue
WITH modularity,
     nodeCount,
     relationshipCount,
     gds.util.asNode(nodeId) AS function,
     propertyValue AS community_id
SET function.leiden_community = community_id
WITH modularity, nodeCount, relationshipCount, community_id, count(*) AS size
RETURN count(*) AS communityCount,
       modularity,
       sum(size) AS functionCount,
       sum(CASE WHEN size = 1 THEN 1 ELSE 0 END) AS singletonCount,
       nodeCount AS projectedNodeCount,
       relationshipCount AS projectedRelationshipCount
"""

# Share of functions left alone in their community above which clustering is
# reported as degenerate.
SINGLETON_RATIO_WARNING_THRESHOLD = 0.25

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
            function_count = summary.get("functionCount", node_count)
            singleton_count = summary.get("singletonCount", 0)
            singleton_ratio = (
                singleton_count / function_count if function_count else 0.0
            )
            logger.info(
                "Leiden clustering completed for %s: functions=%s, "
                "projectedNodes=%s, projectedRelationships=%s, "
                "communityCount=%s, singletons=%s, singletonRatio=%.3f, "
                "modularity=%s",
                normalized_repo_name,
                function_count,
                summary.get("projectedNodeCount"),
                summary.get("projectedRelationshipCount"),
                summary["communityCount"],
                singleton_count,
                singleton_ratio,
                summary["modularity"],
            )
            if singleton_ratio > SINGLETON_RATIO_WARNING_THRESHOLD:
                logger.warning(
                    "Leiden clustering for %s left %.0f%% of functions in "
                    "single-function communities; the projected graph is "
                    "too sparse to group them",
                    normalized_repo_name,
                    singleton_ratio * 100,
                )
            return summary
        finally:
            dropped = await session.run(
                DROP_CODEBASE_GRAPH_QUERY,
                graph_name=graph_name,
            )
            await dropped.consume()
            logger.info("Released GDS projection %s", graph_name)
