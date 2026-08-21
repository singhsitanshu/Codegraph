"""Tests for repository-scoped graph deletion."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.db.graph_ops import (
    DELETE_ALL_REPOSITORY_GRAPHS_QUERY,
    DELETE_REPOSITORY_GRAPH_QUERY,
    delete_all_repository_graphs,
    delete_repository_graph,
)
from app.main import app, lifespan


def test_delete_repository_graph_uses_scoped_detach_delete() -> None:
    transaction = MagicMock()
    transaction.run = AsyncMock()
    transaction.run.return_value.consume = AsyncMock()
    session = MagicMock()

    async def execute_write(callback):
        await callback(transaction)

    session.execute_write = AsyncMock(side_effect=execute_write)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    driver = MagicMock()
    driver.session.return_value = session_context

    with patch("app.db.graph_ops.get_neo4j_driver", return_value=driver):
        asyncio.run(delete_repository_graph(" owner/repository "))

    transaction.run.assert_awaited_once_with(
        DELETE_REPOSITORY_GRAPH_QUERY,
        repo_name="owner/repository",
    )
    transaction.run.return_value.consume.assert_awaited_once_with()
    session.execute_write.assert_awaited_once()


def test_delete_all_repository_graphs_removes_only_scoped_nodes() -> None:
    transaction = MagicMock()
    transaction.run = AsyncMock()
    transaction.run.return_value.consume = AsyncMock()
    session = MagicMock()

    async def execute_write(callback):
        await callback(transaction)

    session.execute_write = AsyncMock(side_effect=execute_write)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    driver = MagicMock()
    driver.session.return_value = session_context

    with patch("app.db.graph_ops.get_neo4j_driver", return_value=driver):
        asyncio.run(delete_all_repository_graphs())

    transaction.run.assert_awaited_once_with(
        DELETE_ALL_REPOSITORY_GRAPHS_QUERY
    )
    transaction.run.return_value.consume.assert_awaited_once_with()


def test_lifespan_cleans_stale_graphs_on_startup() -> None:
    initialize = MagicMock()
    cleanup = AsyncMock()
    close_sync_driver = MagicMock()
    close_async_driver = AsyncMock()

    async def run_lifespan() -> None:
        async with lifespan(app):
            cleanup.assert_awaited_once_with()

    with (
        patch("app.main.initialize_database", new=initialize),
        patch("app.main.delete_all_repository_graphs", new=cleanup),
        patch("app.main.close_driver", new=close_sync_driver),
        patch("app.main.close_neo4j_driver", new=close_async_driver),
    ):
        asyncio.run(run_lifespan())

    initialize.assert_called_once_with()
    close_sync_driver.assert_called_once_with()
    close_async_driver.assert_awaited_once_with()


def test_delete_repository_endpoint_normalizes_and_deletes_scope() -> None:
    delete_graph = AsyncMock()
    with patch("app.main.delete_repository_graph", new=delete_graph):
        response = TestClient(app).delete(
            "/api/repositories/owner%2Frepository.git"
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "repo_name": "owner/repository",
    }
    delete_graph.assert_awaited_once_with("owner/repository")


def test_delete_repository_endpoint_rejects_invalid_scope() -> None:
    delete_graph = AsyncMock()
    with patch("app.main.delete_repository_graph", new=delete_graph):
        response = TestClient(app).delete(
            "/api/repositories/owner/repository/extra"
        )

    assert response.status_code == 422
    delete_graph.assert_not_awaited()


def test_browser_cleanup_endpoint_accepts_json_scope() -> None:
    delete_graph = AsyncMock()
    with patch("app.main.delete_repository_graph", new=delete_graph):
        response = TestClient(app).request(
            "DELETE",
            "/api/repo",
            json={"repo_name": " owner/repository.git "},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "repo_name": "owner/repository",
    }
    delete_graph.assert_awaited_once_with("owner/repository")


def test_browser_cleanup_endpoint_rejects_invalid_scope() -> None:
    delete_graph = AsyncMock()
    with patch("app.main.delete_repository_graph", new=delete_graph):
        response = TestClient(app).request(
            "DELETE",
            "/api/repo",
            json={"repo_name": "not-a-repository"},
        )

    assert response.status_code == 422
    delete_graph.assert_not_awaited()
