"""Tests for repository-scoped graph deletion."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.db.graph_ops import (
    DELETE_REPOSITORY_GRAPH_QUERY,
    delete_repository_graph,
)
from app.main import app


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
