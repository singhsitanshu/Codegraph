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
    assert serialized["file_path"] == "services/payment.py"
    assert serialized["data"]["community"] == 1
    assert serialized["data"]["leiden_community"] == 1
