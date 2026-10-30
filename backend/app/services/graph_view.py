"""The repository graph as the dashboard draws it.

Nodes and edges are serialized for both React Flow and Cytoscape consumers,
and nodes get a starting grid position the client may later re-layout.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from app.db.graph_queries import (
    GraphNode,
    GraphRelationship,
    fetch_repository_graph,
)


GRID_COLUMNS = 8
GRID_COLUMN_WIDTH = 220
GRID_ROW_HEIGHT = 120


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


def serialize_node(node: GraphNode) -> dict[str, Any]:
    """Serialize a stored node for both React Flow and Cytoscape consumers."""

    node_id = node.element_id
    labels = sorted(node.labels)
    properties = _json_value(node.properties)
    properties.pop("raw_code", None)
    properties.pop("embedding", None)
    label = (
        properties.get("qualified_name")
        or properties.get("name")
        or properties.get("path")
        or (labels[0] if labels else node_id)
    )
    community_id = properties.get("leiden_community")
    community_name = node.community_name
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
    # The same fields appear at the top level and override ``data`` properties.
    fields = {
        "id": node_id,
        "label": str(label),
        "labels": labels,
        "community": community_id,
        "community_id": community_id,
        "community_name": resolved_community_name,
        "community_description": node.community_description,
        "file_path": file_path,
    }
    return {**fields, "data": {**properties, **fields}}


def serialize_relationship(relationship: GraphRelationship) -> dict[str, Any]:
    """Serialize a stored relationship as a directed graph edge."""

    properties = _json_value(relationship.properties)
    fields = {
        "id": relationship.element_id,
        "source": relationship.start_node_id,
        "target": relationship.end_node_id,
        "label": relationship.type,
    }
    return {
        **fields,
        "data": {**properties, **fields, "type": relationship.type},
    }


def _grid_position(index: int) -> dict[str, float]:
    return {
        "x": float((index % GRID_COLUMNS) * GRID_COLUMN_WIDTH),
        "y": float((index // GRID_COLUMNS) * GRID_ROW_HEIGHT),
    }


async def fetch_graph_view(repo_name: str) -> dict[str, list[dict[str, Any]]]:
    """Read one repository graph and serialize it for the dashboard."""

    graph = await fetch_repository_graph(repo_name)
    nodes = [
        {**serialize_node(node), "position": _grid_position(index)}
        for index, node in enumerate(graph.nodes)
    ]
    return {
        "nodes": nodes,
        "edges": [
            serialize_relationship(relationship)
            for relationship in graph.relationships
        ],
    }
