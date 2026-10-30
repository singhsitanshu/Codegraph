"""Repository-scoped reads behind the graph dashboard.

Records leave this module as plain data: Neo4j nodes and relationships become
:class:`GraphNode` and :class:`GraphRelationship` values, and how they are laid
out or serialized for a client is decided elsewhere.
"""

from dataclasses import dataclass
from typing import Any

from neo4j.graph import Node, Relationship

from app.db.driver import get_neo4j_driver


GRAPH_QUERY = """
MATCH (file:File {repo_name: $repo_name})
OPTIONAL MATCH (file)-[:DEFINES]->(function:Function {repo_name: $repo_name})
WITH collect(DISTINCT file) + collect(DISTINCT function) AS repository_nodes
UNWIND repository_nodes AS n
OPTIONAL MATCH (n)-[r:DEFINES|CALLS]->(m {repo_name: $repo_name})
OPTIONAL MATCH (n:Function)-[:IN_COMMUNITY]->(
    n_community:Community {repo_name: $repo_name}
)
OPTIONAL MATCH (m:Function)-[:IN_COMMUNITY]->(
    m_community:Community {repo_name: $repo_name}
)
RETURN n,
       r,
       m,
       n_community.name AS n_community_name,
       n_community.description AS n_community_description,
       m_community.name AS m_community_name,
       m_community.description AS m_community_description
LIMIT 200
"""

NODE_CODE_QUERY = """
MATCH (function:Function {repo_name: $repo_name})
WHERE elementId(function) = $node_id
RETURN function.raw_code AS code,
       function.file_path AS file_path,
       function.name AS name
LIMIT 1
"""


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One stored node with the community it belongs to, if any."""

    element_id: str
    labels: frozenset[str]
    properties: dict[str, Any]
    community_name: str | None = None
    community_description: str | None = None


@dataclass(frozen=True, slots=True)
class GraphRelationship:
    """One stored directed relationship between two nodes."""

    element_id: str
    type: str
    start_node_id: str
    end_node_id: str
    properties: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RepositoryGraph:
    """The distinct nodes and relationships of one repository, in query order."""

    nodes: list[GraphNode]
    relationships: list[GraphRelationship]


def _graph_node(
    node: Node,
    community_name: str | None,
    community_description: str | None,
) -> GraphNode:
    return GraphNode(
        element_id=node.element_id,
        labels=frozenset(node.labels),
        properties=dict(node),
        community_name=community_name,
        community_description=community_description,
    )


def _graph_relationship(relationship: Relationship) -> GraphRelationship:
    return GraphRelationship(
        element_id=relationship.element_id,
        type=relationship.type,
        start_node_id=relationship.start_node.element_id,
        end_node_id=relationship.end_node.element_id,
        properties=dict(relationship),
    )


async def fetch_repository_graph(repo_name: str) -> RepositoryGraph:
    """Read one repository's files, functions, and their relationships."""

    nodes: dict[str, GraphNode] = {}
    relationships: dict[str, GraphRelationship] = {}
    async with get_neo4j_driver().session() as session:
        result = await session.run(GRAPH_QUERY, repo_name=repo_name)
        async for record in result:
            node_contexts = (
                (
                    record["n"],
                    record["n_community_name"],
                    record["n_community_description"],
                ),
                (
                    record["m"],
                    record["m_community_name"],
                    record["m_community_description"],
                ),
            )
            for node, community_name, community_description in node_contexts:
                if isinstance(node, Node) and node.element_id not in nodes:
                    nodes[node.element_id] = _graph_node(
                        node,
                        community_name,
                        community_description,
                    )

            relationship = record["r"]
            if (
                isinstance(relationship, Relationship)
                and relationship.element_id not in relationships
            ):
                relationships[relationship.element_id] = _graph_relationship(
                    relationship
                )

    return RepositoryGraph(
        nodes=list(nodes.values()),
        relationships=list(relationships.values()),
    )


async def fetch_node_code(
    node_id: str,
    repo_name: str,
) -> dict[str, str] | None:
    """Fetch one function's source without adding it to the graph payload."""

    async with get_neo4j_driver().session() as session:
        result = await session.run(
            NODE_CODE_QUERY,
            node_id=node_id,
            repo_name=repo_name,
        )
        record = await result.single()
    if record is None:
        return None
    return {
        "code": record["code"] or "",
        "file_path": record["file_path"] or "",
        "name": record["name"] or "",
    }
