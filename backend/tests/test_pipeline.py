"""Mocked FastAPI graph and chat endpoint compatibility tests."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

TEST_REPO_NAME = "test/mock-repository"
TEST_FILE_PATH = "TEST_MOCK_FILE.py"


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
