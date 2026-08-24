"""Tests for graph API node aliases consumed by React Flow."""

from app.db import _serialize_node


class FakeNode(dict):
    element_id = "func_123"
    labels = {"Function"}


def test_function_serialization_exposes_leiden_community_alias() -> None:
    node = FakeNode(
        name="process_payment",
        file_path="services/payment.py",
        leiden_community=1,
    )

    serialized = _serialize_node(node)

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
    node = FakeNode(
        name="process_payment",
        file_path="services/payment.py",
        leiden_community=1,
    )

    serialized = _serialize_node(
        node,
        community_name="Payment Processing",
        community_description="Coordinates customer payment workflows.",
    )

    assert serialized["community_name"] == "Payment Processing"
    assert serialized["community_description"] == (
        "Coordinates customer payment workflows."
    )
    assert serialized["data"]["community_name"] == "Payment Processing"


def test_function_serialization_omits_raw_code_from_graph_payload() -> None:
    node = FakeNode(
        name="process_payment",
        file_path="services/payment.py",
        raw_code="def process_payment():\n    return True",
    )

    serialized = _serialize_node(node)

    assert "raw_code" not in serialized
    assert "raw_code" not in serialized["data"]
