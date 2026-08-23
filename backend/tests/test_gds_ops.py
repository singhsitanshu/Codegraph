"""Unit tests for repository-scoped Leiden community detection."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.db.gds_ops import (
    COUNT_REPOSITORY_FUNCTIONS_QUERY,
    DROP_CODEBASE_GRAPH_QUERY,
    PROJECT_CODEBASE_GRAPH_QUERY,
    RUN_LEIDEN_QUERY,
    run_leiden_clustering,
)


def _mock_driver(results: list[MagicMock]) -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    session.run = AsyncMock(side_effect=results)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    driver = MagicMock()
    driver.session.return_value = session_context
    return driver, session


def _consumable_result() -> MagicMock:
    result = MagicMock()
    result.consume = AsyncMock()
    return result


def _data_result(records: list[dict]) -> MagicMock:
    result = MagicMock()
    result.data = AsyncMock(return_value=records)
    return result


def test_run_leiden_clustering_projects_writes_and_drops_graph() -> None:
    count_result = _data_result([{"node_count": 12}])
    projection = _consumable_result()
    leiden = MagicMock()
    leiden.data = AsyncMock(
        return_value=[{"communityCount": 3, "modularity": 0.42}]
    )
    dropped = _consumable_result()
    driver, session = _mock_driver([count_result, projection, leiden, dropped])

    with patch("app.db.gds_ops.get_neo4j_driver", return_value=driver):
        result = asyncio.run(run_leiden_clustering(" owner/repository "))

    assert result == {"communityCount": 3, "modularity": 0.42}
    graph_name = "codebase_graph_owner/repository"
    assert session.run.await_args_list == [
        call(
            COUNT_REPOSITORY_FUNCTIONS_QUERY,
            repo_name="owner/repository",
        ),
        call(
            PROJECT_CODEBASE_GRAPH_QUERY,
            graph_name=graph_name,
            repo_name="owner/repository",
        ),
        call(RUN_LEIDEN_QUERY, graph_name=graph_name),
        call(DROP_CODEBASE_GRAPH_QUERY, graph_name=graph_name),
    ]
    projection.consume.assert_awaited_once_with()
    dropped.consume.assert_awaited_once_with()


def test_projection_uses_modern_undirected_cypher_aggregation() -> None:
    assert "gds.graph.project.cypher" not in PROJECT_CODEBASE_GRAPH_QUERY
    assert "WITH gds.graph.project(" in PROJECT_CODEBASE_GRAPH_QUERY
    assert "OPTIONAL MATCH" in PROJECT_CODEBASE_GRAPH_QUERY
    assert "undirectedRelationshipTypes: ['*']" in PROJECT_CODEBASE_GRAPH_QUERY
    assert "gds.graph.drop($graph_name, false)" in DROP_CODEBASE_GRAPH_QUERY


def test_run_leiden_clustering_drops_graph_when_algorithm_fails() -> None:
    count_result = _data_result([{"node_count": 12}])
    projection = _consumable_result()
    leiden = MagicMock()
    leiden.data = AsyncMock(side_effect=RuntimeError("GDS failed"))
    dropped = _consumable_result()
    driver, session = _mock_driver([count_result, projection, leiden, dropped])

    with (
        patch("app.db.gds_ops.get_neo4j_driver", return_value=driver),
        pytest.raises(RuntimeError, match="GDS failed"),
    ):
        asyncio.run(run_leiden_clustering("owner/repository"))

    assert session.run.await_count == 4
    dropped.consume.assert_awaited_once_with()


def test_run_leiden_clustering_drops_graph_when_projection_consume_fails() -> None:
    count_result = _data_result([{"node_count": 12}])
    projection = _consumable_result()
    projection.consume = AsyncMock(side_effect=RuntimeError("projection failed"))
    dropped = _consumable_result()
    driver, session = _mock_driver([count_result, projection, dropped])

    with (
        patch("app.db.gds_ops.get_neo4j_driver", return_value=driver),
        pytest.raises(RuntimeError, match="projection failed"),
    ):
        asyncio.run(run_leiden_clustering("owner/repository"))

    assert session.run.await_args_list == [
        call(
            COUNT_REPOSITORY_FUNCTIONS_QUERY,
            repo_name="owner/repository",
        ),
        call(
            PROJECT_CODEBASE_GRAPH_QUERY,
            graph_name="codebase_graph_owner/repository",
            repo_name="owner/repository",
        ),
        call(
            DROP_CODEBASE_GRAPH_QUERY,
            graph_name="codebase_graph_owner/repository",
        ),
    ]
    dropped.consume.assert_awaited_once_with()


def test_run_leiden_clustering_skips_empty_repository(caplog) -> None:
    count_result = _data_result([{"node_count": 0}])
    driver, session = _mock_driver([count_result])

    with patch("app.db.gds_ops.get_neo4j_driver", return_value=driver):
        result = asyncio.run(run_leiden_clustering("owner/empty"))

    assert result == {"communityCount": 0, "modularity": 0.0}
    session.run.assert_awaited_once_with(
        COUNT_REPOSITORY_FUNCTIONS_QUERY,
        repo_name="owner/empty",
    )
    assert "Skipping clustering for owner/empty: 0 nodes found" in caplog.text


def test_run_leiden_clustering_rejects_blank_repository() -> None:
    with pytest.raises(ValueError, match="repo_name must not be blank"):
        asyncio.run(run_leiden_clustering("  "))
