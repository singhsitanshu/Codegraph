"""Integration tests for Neo4j persistence and FastAPI graph/chat endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db import close_neo4j_driver
from app.db import neo4j_client
from app.db.graph_ops import save_parsed_ast_to_neo4j
from app.main import app

TEST_FILE_PATH = "TEST_MOCK_FILE.py"
MOCK_DATA: list[dict[str, object]] = [
    {
        "file_path": TEST_FILE_PATH,
        "defined_functions": ["mock_func_A", "mock_func_B"],
        "outgoing_calls": ["mock_func_B", "external_api_call"],
    }
]
TEST_NODE_CLEANUP_QUERY = (
    "MATCH (n) WHERE n.path = 'TEST_MOCK_FILE.py' "
    "OR n.file = 'TEST_MOCK_FILE.py' DETACH DELETE n"
)
ORPHAN_EXTERNAL_CLEANUP_QUERY = """
MATCH (function:Function {name: 'external_api_call', external: true})
WHERE NOT (function)<-[:CALLS]-()
DETACH DELETE function
"""


def _cleanup_test_nodes() -> None:
    """Delete mock graph data so every database test is isolated."""
    if neo4j_client.driver is None:
        pytest.skip("Neo4j is unavailable; integration tests require a live database")

    with neo4j_client.driver.session() as session:
        session.run(TEST_NODE_CLEANUP_QUERY).consume()
        session.run(ORPHAN_EXTERNAL_CLEANUP_QUERY).consume()


@pytest.fixture
def db_cleanup() -> Iterator[None]:
    """Clean test nodes before and after each Neo4j integration test."""
    _cleanup_test_nodes()
    yield
    _cleanup_test_nodes()


def _save_mock_ast() -> None:
    """Run async graph persistence safely from a synchronous pytest test."""

    async def save() -> None:
        try:
            await save_parsed_ast_to_neo4j(MOCK_DATA)
        finally:
            await close_neo4j_driver()

    asyncio.run(save())


def test_neo4j_ast_write(db_cleanup: None) -> None:
    """Persist mock AST data through explicit transactions and verify the graph."""
    _save_mock_ast()
    assert neo4j_client.driver is not None

    with neo4j_client.driver.session() as session:
        file_count = session.run(
            "MATCH (file:File {path: $path}) RETURN count(file) AS count",
            path=TEST_FILE_PATH,
        ).single(strict=True)["count"]
        function_count = session.run(
            "MATCH (function:Function {file: $path}) "
            "RETURN count(function) AS count",
            path=TEST_FILE_PATH,
        ).single(strict=True)["count"]
        calls_count = session.run(
            "MATCH (:Function {name: 'mock_func_A', file: $path})"
            "-[calls:CALLS]->"
            "(:Function {name: 'mock_func_B', file: $path}) "
            "RETURN count(calls) AS count",
            path=TEST_FILE_PATH,
        ).single(strict=True)["count"]

    assert file_count == 1
    assert function_count == 2
    assert calls_count == 1


def test_api_graph_endpoint(db_cleanup: None) -> None:
    """Expose persisted mock AST data in the React Flow graph response."""
    _save_mock_ast()
    client = TestClient(app)

    response = client.get("/api/graph")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("nodes"), list)
    assert isinstance(payload.get("edges"), list)
    assert any(
        node.get("label") == TEST_FILE_PATH
        or node.get("data", {}).get("label") == TEST_FILE_PATH
        for node in payload["nodes"]
    )


def test_api_chat_endpoint() -> None:
    """Return the mocked LangGraph result without calling Claude."""
    client = TestClient(app)

    with patch(
        "app.main.ask_code_agent",
        new=AsyncMock(return_value="Mocked LangGraph response"),
    ):
        response = client.post(
            "/api/chat",
            json={"message": "What calls mock_func?"},
        )

    assert response.status_code == 200
    assert response.json() == {"response": "Mocked LangGraph response"}
