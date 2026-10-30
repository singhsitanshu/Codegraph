"""Tests for graph API node aliases consumed by React Flow."""

from app.db.graph_queries import GraphNode
from app.services.graph_view import serialize_node


def _node(
    community_name: str | None = None,
    community_description: str | None = None,
    **properties: object,
) -> GraphNode:
    return GraphNode(
        element_id="func_123",
        labels=frozenset({"Function"}),
        properties=properties,
        community_name=community_name,
        community_description=community_description,
    )


def test_function_serialization_exposes_leiden_community_alias() -> None:
    node = _node(
        name="process_payment",
        file_path="services/payment.py",
        leiden_community=1,
    )

    serialized = serialize_node(node)

    assert serialized["id"] == "func_123"
    assert serialized["label"] == "process_payment"
    assert serialized["community"] == 1
    assert serialized["community_id"] == 1
    assert serialized["community_name"] == "Cluster #1"
    assert serialized["community_description"] is None
    assert serialized["file_path"] == "services/payment.py"
    assert serialized["data"]["community"] == 1
    assert serialized["data"]["community_id"] == 1
    assert serialized["data"]["community_name"] == "Cluster #1"
    assert serialized["data"]["leiden_community"] == 1


def test_function_serialization_exposes_stored_community_metadata() -> None:
    node = _node(
        community_name="Payment Processing",
        community_description="Coordinates customer payment workflows.",
        name="process_payment",
        file_path="services/payment.py",
        leiden_community=1,
    )

    serialized = serialize_node(node)

    assert serialized["community_name"] == "Payment Processing"
    assert serialized["community_description"] == (
        "Coordinates customer payment workflows."
    )
    assert serialized["data"]["community_name"] == "Payment Processing"


def test_function_serialization_omits_source_and_embedding_from_graph_payload() -> None:
    node = _node(
        name="process_payment",
        file_path="services/payment.py",
        raw_code="def process_payment():\n    return True",
        embedding=[0.1, 0.2],
    )

    serialized = serialize_node(node)

    assert "raw_code" not in serialized
    assert "raw_code" not in serialized["data"]
    assert "embedding" not in serialized
    assert "embedding" not in serialized["data"]


def test_function_serialization_exposes_stable_id_alongside_element_id() -> None:
    node = _node(
        name="validate",
        qualified_name="PaymentService.validate",
        file_path="src/payments.py",
        entity_id="fn:v1:stable",
    )

    serialized = serialize_node(node)

    assert serialized["id"] == "func_123"
    assert serialized["data"]["entity_id"] == "fn:v1:stable"
    assert serialized["data"]["qualified_name"] == "PaymentService.validate"
    assert serialized["label"] == "PaymentService.validate"
