"""Async Neo4j connection and graph serialization utilities."""

from collections.abc import Mapping, Sequence
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.graph import Node, Relationship

from app.config import settings


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

REPOSITORY_TOKEN_QUERY = """
MATCH (repository:Repository {repo_name: $repo_name})
RETURN coalesce(repository.total_tokens, 0) AS total_tokens
LIMIT 1
"""

_driver: AsyncDriver | None = None


def get_neo4j_driver() -> AsyncDriver:
    """Return the process-wide Neo4j driver, creating it on first use."""

    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


async def close_neo4j_driver() -> None:
    """Close the process-wide Neo4j driver during application shutdown."""

    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


def _json_value(value: Any) -> Any:
    """Convert Neo4j property values into JSON-compatible Python values."""

    if value is None or isinstance(value, (bool, float, int, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    iso_format = getattr(value, "iso_format", None)
    if callable(iso_format):
        return iso_format()
    return str(value)


def _serialize_node(
    node: Node,
    community_name: str | None = None,
    community_description: str | None = None,
) -> dict[str, Any]:
    """Serialize a Neo4j node for both React Flow and Cytoscape consumers."""

    node_id = node.element_id
    labels = sorted(node.labels)
    properties = _json_value(dict(node))
    properties.pop("raw_code", None)
    properties.pop("embedding", None)
    label = (
        properties.get("qualified_name")
        or properties.get("name")
        or properties.get("path")
        or (labels[0] if labels else node_id)
    )
    community_id = properties.get("leiden_community")
    resolved_community_name = (
        community_name.strip()
        if isinstance(community_name, str) and community_name.strip()
        else (
            f"Cluster #{community_id}"
            if community_id is not None
            else None
        )
    )
    file_path = properties.get("file_path") or properties.get("path")
    data = {
        **properties,
        "id": node_id,
        "label": str(label),
        "labels": labels,
        "community": community_id,
        "community_id": community_id,
        "community_name": resolved_community_name,
        "community_description": community_description,
        "file_path": file_path,
    }
    return {
        "id": node_id,
        "label": str(label),
        "labels": labels,
        "community": community_id,
        "community_id": community_id,
        "community_name": resolved_community_name,
        "community_description": community_description,
        "file_path": file_path,
        "data": data,
    }


def _serialize_relationship(relationship: Relationship) -> dict[str, Any]:
    """Serialize a Neo4j relationship as a directed graph edge."""

    edge_id = relationship.element_id
    source = relationship.start_node.element_id
    target = relationship.end_node.element_id
    relationship_type = relationship.type
    properties = _json_value(dict(relationship))
    data = {
        **properties,
        "id": edge_id,
        "source": source,
        "target": target,
        "label": relationship_type,
        "type": relationship_type,
    }
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "label": relationship_type,
        "data": data,
    }


async def fetch_graph_data(repo_name: str) -> dict[str, list[dict[str, Any]]]:
    """Query and serialize one repository's Neo4j graph."""

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
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
                    nodes[node.element_id] = _serialize_node(
                        node,
                        community_name=community_name,
                        community_description=community_description,
                    )

            relationship = record["r"]
            if (
                isinstance(relationship, Relationship)
                and relationship.element_id not in edges
            ):
                edges[relationship.element_id] = _serialize_relationship(
                    relationship
                )

    serialized_nodes = list(nodes.values())
    for index, node in enumerate(serialized_nodes):
        node["position"] = {
            "x": float((index % 8) * 220),
            "y": float((index // 8) * 120),
        }

    return {"nodes": serialized_nodes, "edges": list(edges.values())}


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
