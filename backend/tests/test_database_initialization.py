"""Tests for idempotent Neo4j schema initialization."""

from unittest.mock import MagicMock, patch

from app.db import neo4j_client


def test_initialize_database_creates_and_awaits_indexes_once() -> None:
    result = MagicMock()
    session = MagicMock()
    session.run.return_value = result
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    driver = MagicMock()
    driver.session.return_value = session_context

    with (
        patch.object(neo4j_client, "driver", driver),
        patch.object(neo4j_client, "_database_initialized", False),
    ):
        neo4j_client.initialize_database()
        neo4j_client.initialize_database()

    expected_queries = [
        *neo4j_client.DATABASE_INDEX_QUERIES,
        neo4j_client.AWAIT_INDEXES_QUERY,
    ]
    assert [call.args[0] for call in session.run.call_args_list] == expected_queries
    assert result.consume.call_count == len(expected_queries)
    driver.session.assert_called_once_with()
