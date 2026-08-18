"""Integration tests for Neo4j persistence and FastAPI graph/chat endpoints."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agent.graph import query_graph_blast_radius
from app.db import close_neo4j_driver, neo4j_client
from app.db.graph_ops import save_parsed_ast_to_neo4j
from app.main import app

TEST_FILE_PATH = "TEST_MOCK_FILE.py"
TEST_REPO_NAME = "test/mock-repository"
OTHER_TEST_REPO_NAME = "test/other-repository"
MOCK_DATA: list[dict[str, object]] = [
    {
        "file_path": TEST_FILE_PATH,
        "defined_functions": ["mock_func_A", "mock_func_B"],
        "outgoing_calls": ["mock_func_B", "external_api_call"],
    }
]
TEST_NODE_CLEANUP_QUERY = (
    "MATCH (n) WHERE n.repo_name IN "
    "['test/mock-repository', 'test/other-repository'] AND ("
    "n.path = 'TEST_MOCK_FILE.py' "
    "OR n.file = 'TEST_MOCK_FILE.py') DETACH DELETE n"
)
ORPHAN_EXTERNAL_CLEANUP_QUERY = """
MATCH (function:Function {
    name: 'external_api_call',
    external: true,
    repo_name: 'test/mock-repository'
})
WHERE NOT (function)<-[:CALLS]-()
DETACH DELETE function
"""


def _cleanup_test_nodes() -> None:
    """Delete mock graph data so every database test is isolated."""
    if neo4j_client.driver is None:
        neo4j_client.driver = neo4j_client._initialize_driver()
    if neo4j_client.driver is None:
        pytest.skip("Neo4j is unavailable; integration tests require a live database")

    with neo4j_client.driver.session() as session:
        session.run(TEST_NODE_CLEANUP_QUERY).consume()
        session.run(ORPHAN_EXTERNAL_CLEANUP_QUERY).consume()


@pytest.fixture
def db_cleanup() -> Iterator[None]:
    """Clean test nodes before and after each Neo4j integration test."""
    _cleanup_test_nodes()
    try:
        yield
    finally:
        _cleanup_test_nodes()
        neo4j_client.close_driver()


def _save_mock_ast() -> None:
    """Run async graph persistence safely from a synchronous pytest test."""

    async def save() -> None:
        try:
            await save_parsed_ast_to_neo4j(MOCK_DATA, repo_name=TEST_REPO_NAME)
        finally:
            await close_neo4j_driver()

    asyncio.run(save())


def test_neo4j_ast_write(db_cleanup: None) -> None:
    """Persist mock AST data through explicit transactions and verify the graph."""
    _save_mock_ast()
    assert neo4j_client.driver is not None

    with neo4j_client.driver.session() as session:
        file_count = session.run(
            "MATCH (file:File {path: $path, repo_name: $repo_name}) "
            "RETURN count(file) AS count",
            path=TEST_FILE_PATH,
            repo_name=TEST_REPO_NAME,
        ).single(strict=True)["count"]
        function_count = session.run(
            "MATCH (function:Function {file: $path, repo_name: $repo_name}) "
            "RETURN count(function) AS count",
            path=TEST_FILE_PATH,
            repo_name=TEST_REPO_NAME,
        ).single(strict=True)["count"]
        calls_count = session.run(
            "MATCH (:Function {name: 'mock_func_A', file: $path, "
            "repo_name: $repo_name})"
            "-[calls:CALLS]->"
            "(:Function {name: 'mock_func_B', file: $path, "
            "repo_name: $repo_name}) "
            "RETURN count(calls) AS count",
            path=TEST_FILE_PATH,
            repo_name=TEST_REPO_NAME,
        ).single(strict=True)["count"]
        external_count = session.run(
            "MATCH (function:Function:ExternalFunction {"
            "name: 'external_api_call', repo_name: $repo_name, "
            "is_external: true}) RETURN count(function) AS count",
            repo_name=TEST_REPO_NAME,
        ).single(strict=True)["count"]

    assert file_count == 1
    assert function_count == 2
    assert calls_count == 1
    assert external_count == 1


def test_api_graph_endpoint(db_cleanup: None) -> None:
    """Expose persisted mock AST data in the React Flow graph response."""
    _save_mock_ast()
    with TestClient(app) as client:
        response = client.get(
            "/api/graph",
            params={"repo_name": TEST_REPO_NAME},
        )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("nodes"), list)
    assert isinstance(payload.get("edges"), list)
    assert any(
        node.get("label") == TEST_FILE_PATH
        or node.get("data", {}).get("label") == TEST_FILE_PATH
        for node in payload["nodes"]
    )


def test_api_graph_is_blank_without_repository_scope() -> None:
    """Do not query Neo4j or expose legacy nodes before repository selection."""

    graph_fetch = AsyncMock(return_value={"nodes": ["legacy"], "edges": []})
    with patch("app.main.fetch_graph_data", new=graph_fetch):
        response = TestClient(app).get("/api/graph")

    assert response.status_code == 200
    assert response.json() == {"nodes": [], "edges": []}
    graph_fetch.assert_not_awaited()


def test_api_graph_passes_normalized_repository_scope() -> None:
    """Fetch only the graph associated with the requested repository."""

    expected = {"nodes": [{"id": "scoped"}], "edges": []}
    graph_fetch = AsyncMock(return_value=expected)
    with patch("app.main.fetch_graph_data", new=graph_fetch):
        response = TestClient(app).get(
            "/api/graph",
            params={"repo_name": " test/mock-repository "},
        )

    assert response.status_code == 200
    assert response.json() == expected
    graph_fetch.assert_awaited_once_with(TEST_REPO_NAME)


def test_api_chat_endpoint() -> None:
    """Return the mocked LangGraph result without calling Claude."""
    client = TestClient(app)

    with patch(
        "app.main.ask_code_agent",
        new=AsyncMock(return_value="Mocked LangGraph response"),
    ):
        response = client.post(
            "/api/chat",
            json={
                "message": "What calls mock_func?",
                "repo_name": TEST_REPO_NAME,
            },
        )

    assert response.status_code == 200
    assert response.json() == {"response": "Mocked LangGraph response"}


def test_api_chat_rejects_unscoped_frontend_payload() -> None:
    """Keep the required repository context visible in the API contract."""

    code_agent = AsyncMock(return_value="This must not be called")
    with patch("app.main.ask_code_agent", new=code_agent):
        response = TestClient(app).post(
            "/api/chat",
            json={"message": "What calls mock_func?"},
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "repo_name"]
    code_agent.assert_not_awaited()


def test_blast_radius_does_not_cross_repository_boundaries(
    db_cleanup: None,
) -> None:
    """Return callers from repository A without leaking repository B."""

    repository_a = [
        {
            "file_path": TEST_FILE_PATH,
            "defined_functions": ["caller_from_a", "shared_target"],
            "outgoing_calls": ["shared_target"],
        }
    ]
    repository_b = [
        {
            "file_path": TEST_FILE_PATH,
            "defined_functions": ["caller_from_b", "shared_target"],
            "outgoing_calls": ["shared_target"],
        }
    ]

    async def save_and_query() -> tuple[dict[str, object], dict[str, object]]:
        try:
            await save_parsed_ast_to_neo4j(repository_b, OTHER_TEST_REPO_NAME)
            await save_parsed_ast_to_neo4j(
                repository_a,
                TEST_REPO_NAME,
                replace_existing=True,
            )
            result_a = await query_graph_blast_radius.ainvoke(
                {
                    "repo_name": TEST_REPO_NAME,
                    "function_name": "shared_target",
                }
            )
            result_b = await query_graph_blast_radius.ainvoke(
                {
                    "repo_name": OTHER_TEST_REPO_NAME,
                    "function_name": "shared_target",
                }
            )
            return json.loads(result_a), json.loads(result_b)
        finally:
            await close_neo4j_driver()

    payload_a, payload_b = asyncio.run(save_and_query())
    caller_names_a = {
        caller["caller"]
        for caller in payload_a["callers"]
        if isinstance(caller, dict)
    }
    caller_names_b = {
        caller["caller"]
        for caller in payload_b["callers"]
        if isinstance(caller, dict)
    }
    assert "caller_from_a" in caller_names_a
    assert "caller_from_b" not in caller_names_a
    assert "caller_from_b" in caller_names_b
    assert "caller_from_a" not in caller_names_b
