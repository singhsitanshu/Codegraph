"""Tests for idempotent Neo4j schema initialization."""

import asyncio
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

from app.db import neo4j_client
from app.utils.embeddings import EMBEDDING_DIMENSIONS, FUNCTION_EMBEDDING_INDEX


def test_initialize_database_creates_and_awaits_indexes() -> None:
    result = MagicMock()
    result.consume = AsyncMock()
    session = MagicMock()
    session.run = AsyncMock(return_value=result)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    driver = MagicMock()
    driver.session.return_value = session_context

    with patch.object(neo4j_client, "get_neo4j_driver", return_value=driver):
        asyncio.run(neo4j_client.initialize_database())

    expected_queries = [
        *neo4j_client.DATABASE_INDEX_QUERIES,
        neo4j_client.AWAIT_INDEXES_QUERY,
    ]
    assert [call.args[0] for call in session.run.await_args_list] == expected_queries
    assert result.consume.await_count == len(expected_queries)
    driver.session.assert_called_once_with()


def test_vector_index_matches_the_embedding_contract() -> None:
    vector_index_query = neo4j_client.DATABASE_INDEX_QUERIES[-1]

    assert f"VECTOR INDEX `{FUNCTION_EMBEDDING_INDEX}`" in vector_index_query
    assert f"`vector.dimensions`: {EMBEDDING_DIMENSIONS}," in vector_index_query


def test_importing_the_schema_module_does_not_connect() -> None:
    with (
        patch("neo4j.GraphDatabase.driver") as sync_driver,
        patch("neo4j.AsyncGraphDatabase.driver") as async_driver,
    ):
        importlib.reload(neo4j_client)

    sync_driver.assert_not_called()
    async_driver.assert_not_called()
