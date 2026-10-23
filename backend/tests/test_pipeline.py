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
from app.db.graph_ops import delete_repository_graph, save_parsed_ast_to_neo4j
from app.main import app
from app.services.parser_service import CodeParser

TEST_FILE_PATH = "TEST_MOCK_FILE.py"
TEST_REPO_NAME = "test/mock-repository"
OTHER_TEST_REPO_NAME = "test/other-repository"
MOCK_FUNC_A_SOURCE = (
    "def mock_func_A():\n"
    "    external_api_call()\n"
    "    return mock_func_B()"
)


def _parse(
    source: str,
    repo_name: str = TEST_REPO_NAME,
    file_path: str = TEST_FILE_PATH,
) -> dict[str, object]:
    return asyncio.run(
        CodeParser().parse_file(
            file_path,
            source.encode("utf-8"),
            repository=repo_name,
        )
    )


MOCK_DATA: list[dict[str, object]] = [
    _parse(MOCK_FUNC_A_SOURCE + "\n\ndef mock_func_B():\n    return True\n")
]


async def _fake_embeddings(texts: list[str]) -> list[list[float]]:
    return [[0.1, 0.2, 0.3] for _ in texts]


TEST_NODE_CLEANUP_QUERY = (
    "MATCH (n) WHERE n.repo_name IN "
    "['test/mock-repository', 'test/other-repository'] "
    "DETACH DELETE n"
)
ORPHAN_EXTERNAL_CLEANUP_QUERY = """
MATCH (function:ExternalFunction {
    name: 'external_api_call',
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

    with patch(
        "app.db.graph_ops.generate_embeddings",
        side_effect=_fake_embeddings,
    ), patch(
        "app.db.graph_ops.run_leiden_clustering",
        new=AsyncMock(),
    ), patch(
        "app.db.graph_ops.label_and_store_communities",
        new=AsyncMock(),
    ):
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
            "MATCH (function:ExternalFunction {"
            "name: 'external_api_call', repo_name: $repo_name, "
            "is_external: true}) WHERE NOT function:Function "
            "RETURN count(function) AS count",
            repo_name=TEST_REPO_NAME,
        ).single(strict=True)["count"]
        identified_count = session.run(
            "MATCH (function:Function {repo_name: $repo_name}) "
            "WHERE function.entity_id STARTS WITH 'fn:v1:' "
            "RETURN count(function) AS count",
            repo_name=TEST_REPO_NAME,
        ).single(strict=True)["count"]
        stored_source = session.run(
            "MATCH (function:Function {name: 'mock_func_A', "
            "repo_name: $repo_name}) RETURN function.raw_code AS raw_code",
            repo_name=TEST_REPO_NAME,
        ).single(strict=True)["raw_code"]

    assert file_count == 1
    assert function_count == 2
    assert calls_count == 1
    assert external_count == 1
    assert identified_count == 2
    assert stored_source == MOCK_FUNC_A_SOURCE


def test_api_graph_endpoint(db_cleanup: None) -> None:
    """Expose persisted mock AST data in the React Flow graph response."""
    _save_mock_ast()
    with patch("app.main.delete_all_repository_graphs", new=AsyncMock()):
        with TestClient(app) as client:
            response = client.get(
                "/api/graph",
                params={"repo_name": TEST_REPO_NAME},
            )
            payload = response.json()
            function_node = next(
                node
                for node in payload["nodes"]
                if node.get("label") == "mock_func_A"
            )
            source_response = client.get(
                f"/api/node/{function_node['id']}/code",
                params={"repo_name": TEST_REPO_NAME},
            )

    assert response.status_code == 200
    assert isinstance(payload.get("nodes"), list)
    assert isinstance(payload.get("edges"), list)
    assert any(
        node.get("label") == TEST_FILE_PATH
        or node.get("data", {}).get("label") == TEST_FILE_PATH
        for node in payload["nodes"]
    )
    assert source_response.status_code == 200
    assert source_response.json() == {
        "code": MOCK_FUNC_A_SOURCE,
        "file_path": TEST_FILE_PATH,
        "name": "mock_func_A",
    }


def test_delete_repository_graph_removes_only_scoped_nodes(
    db_cleanup: None,
) -> None:
    """Delete the live test repository graph without touching other scopes."""

    _save_mock_ast()

    async def delete() -> None:
        try:
            await delete_repository_graph(TEST_REPO_NAME)
        finally:
            await close_neo4j_driver()

    asyncio.run(delete())
    assert neo4j_client.driver is not None
    with neo4j_client.driver.session() as session:
        remaining_nodes = session.run(
            "MATCH (node {repo_name: $repo_name}) RETURN count(node) AS count",
            repo_name=TEST_REPO_NAME,
        ).single(strict=True)["count"]

    assert remaining_nodes == 0


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


def test_api_node_code_is_repository_scoped() -> None:
    """Fetch source by graph node ID without exposing another repository."""

    expected = {
        "code": "def mock_func_A():\n    return True",
        "file_path": TEST_FILE_PATH,
        "name": "mock_func_A",
    }
    source_fetch = AsyncMock(return_value=expected)
    with patch("app.main.fetch_node_code", new=source_fetch):
        response = TestClient(app).get(
            "/api/node/4%3Aabc%3A12/code",
            params={"repo_name": " test/mock-repository "},
        )

    assert response.status_code == 200
    assert response.json() == expected
    source_fetch.assert_awaited_once_with("4:abc:12", TEST_REPO_NAME)


def test_api_node_code_returns_404_for_unknown_function() -> None:
    source_fetch = AsyncMock(return_value=None)
    with patch("app.main.fetch_node_code", new=source_fetch):
        response = TestClient(app).get(
            "/api/node/missing/code",
            params={"repo_name": TEST_REPO_NAME},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Source code was not found for this function"
    )


def test_api_node_code_requires_repository_scope() -> None:
    source_fetch = AsyncMock()
    with patch("app.main.fetch_node_code", new=source_fetch):
        response = TestClient(app).get("/api/node/function-id/code")

    assert response.status_code == 422
    source_fetch.assert_not_awaited()


def test_api_chat_endpoint() -> None:
    """Return the mocked LangGraph result without calling Claude."""
    client = TestClient(app)

    with patch(
        "app.main.ask_code_agent_with_metrics",
        new=AsyncMock(
            return_value={
                "answer": "Mocked LangGraph response",
                "metrics": {
                    "full_repo_tokens": 1_000,
                    "context_tokens": 100,
                    "tokens_saved": 900,
                    "efficiency_percentage": 90.0,
                },
            }
        ),
    ):
        response = client.post(
            "/api/chat",
            json={
                "message": "What calls mock_func?",
                "repo_name": TEST_REPO_NAME,
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "response": "Mocked LangGraph response",
        "metrics": {
            "full_repo_tokens": 1_000,
            "context_tokens": 100,
            "tokens_saved": 900,
            "efficiency_percentage": 90.0,
        },
    }


def test_api_chat_rejects_unscoped_frontend_payload() -> None:
    """Keep the required repository context visible in the API contract."""

    code_agent = AsyncMock(return_value="This must not be called")
    with patch("app.main.ask_code_agent_with_metrics", new=code_agent):
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

    shared_source = "\n\ndef shared_target():\n    pass\n"
    repository_a = [
        _parse("def caller_from_a():\n    shared_target()" + shared_source)
    ]
    repository_b = [
        _parse(
            "def caller_from_b():\n    shared_target()" + shared_source,
            repo_name=OTHER_TEST_REPO_NAME,
        )
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

    with patch(
        "app.db.graph_ops.generate_embeddings",
        side_effect=_fake_embeddings,
    ), patch(
        "app.db.graph_ops.run_leiden_clustering",
        new=AsyncMock(),
    ), patch(
        "app.db.graph_ops.label_and_store_communities",
        new=AsyncMock(),
    ):
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


def test_initialize_database_creates_function_identity_constraint() -> None:
    """The entity_id uniqueness constraint is accepted by the live database."""

    if neo4j_client.driver is None:
        neo4j_client.driver = neo4j_client._initialize_driver()
    if neo4j_client.driver is None:
        pytest.skip("Neo4j is unavailable; integration tests require a live database")

    with patch.object(neo4j_client, "_database_initialized", False):
        neo4j_client.initialize_database()
    with neo4j_client.driver.session() as session:
        constraint = session.run(
            "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties "
            "WHERE name = 'function_entity_id' "
            "RETURN type, labelsOrTypes, properties"
        ).single()
    neo4j_client.close_driver()

    assert constraint is not None
    assert constraint["labelsOrTypes"] == ["Function"]
    assert constraint["properties"] == ["entity_id"]


def test_incremental_update_keeps_identity_and_incoming_edges(
    db_cleanup: None,
) -> None:
    """A body edit keeps the node; removed definitions and files disappear."""

    library_path = "src/library.py"
    first_version = [
        _parse(
            "def target():\n    pass\n\ndef removed():\n    pass\n",
            file_path=library_path,
        ),
        _parse("def caller():\n    target()\n", file_path="src/app.py"),
        _parse("def obsolete():\n    pass\n", file_path="src/obsolete.py"),
    ]
    second_version = [
        _parse("def target():\n    return 1\n", file_path=library_path)
    ]
    target_id = second_version[0]["functions"][0]["entity_id"]
    assert target_id == first_version[0]["functions"][0]["entity_id"]

    async def save() -> None:
        try:
            await save_parsed_ast_to_neo4j(
                first_version, TEST_REPO_NAME, replace_existing=True
            )
            await save_parsed_ast_to_neo4j(
                second_version,
                TEST_REPO_NAME,
                deleted_file_paths=["src/obsolete.py"],
            )
        finally:
            await close_neo4j_driver()

    with patch(
        "app.db.graph_ops.generate_embeddings",
        side_effect=_fake_embeddings,
    ), patch(
        "app.db.graph_ops.run_leiden_clustering",
        new=AsyncMock(),
    ), patch(
        "app.db.graph_ops.label_and_store_communities",
        new=AsyncMock(),
    ):
        asyncio.run(save())

    assert neo4j_client.driver is not None
    with neo4j_client.driver.session() as session:
        functions = session.run(
            "MATCH (function:Function {repo_name: $repo_name}) "
            "RETURN function.qualified_name AS name, "
            "function.entity_id AS entity_id, function.raw_code AS raw_code "
            "ORDER BY name",
            repo_name=TEST_REPO_NAME,
        ).data()
        files = session.run(
            "MATCH (file:File {repo_name: $repo_name}) "
            "RETURN file.path AS path ORDER BY path",
            repo_name=TEST_REPO_NAME,
        ).value()
        incoming = session.run(
            "MATCH (:Function {repo_name: $repo_name, name: 'caller'})"
            "-[call:CALLS]->(target:Function {entity_id: $target_id}) "
            "RETURN call.resolution AS resolution",
            repo_name=TEST_REPO_NAME,
            target_id=target_id,
        ).value()

    assert [function["name"] for function in functions] == ["caller", "target"]
    assert functions[1]["entity_id"] == target_id
    assert functions[1]["raw_code"] == "def target():\n    return 1"
    assert files == ["src/app.py", library_path]
    assert incoming == ["repository_unique"]

