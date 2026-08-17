"""Async Neo4j connection and graph serialization utilities."""

from collections.abc import Mapping, Sequence
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.graph import Node, Relationship

from app.config import settings


GRAPH_QUERY = """
MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN n, r, m
LIMIT 200
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


def _serialize_node(node: Node) -> dict[str, Any]:
    """Serialize a Neo4j node for both React Flow and Cytoscape consumers."""

    node_id = node.element_id
    labels = sorted(node.labels)
    properties = _json_value(dict(node))
    label = (
        properties.get("qualified_name")
        or properties.get("name")
        or properties.get("path")
        or (labels[0] if labels else node_id)
    )
    data = {
        **properties,
        "id": node_id,
        "label": str(label),
        "labels": labels,
    }
    return {
        "id": node_id,
        "labels": labels,
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


async def fetch_graph_data() -> dict[str, list[dict[str, Any]]]:
    """Query and serialize up to 200 Neo4j graph records."""

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    async with get_neo4j_driver().session() as session:
        result = await session.run(GRAPH_QUERY)
        async for record in result:
            for node in (record["n"], record["m"]):
                if isinstance(node, Node) and node.element_id not in nodes:
                    nodes[node.element_id] = _serialize_node(node)

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
