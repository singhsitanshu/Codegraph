"""Unit coverage for repository-scoped, micro-batched Neo4j writes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.db import GRAPH_QUERY
from app.db.graph_ops import (
    DELETE_REPOSITORY_QUERY,
    MERGE_CALLS_QUERY,
    MERGE_FILES_QUERY,
    MERGE_FUNCTIONS_QUERY,
    TAG_EXTERNAL_FUNCTIONS_QUERY,
    chunk_data,
    save_parsed_ast_to_neo4j,
)


def _mock_driver():
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
    return driver, session, transaction


async def _fake_embeddings(texts: list[str]) -> list[list[float]]:
    return [[0.1, 0.2, 0.3] for _ in texts]


def test_graph_read_starts_from_repository_scoped_files() -> None:
    assert "MATCH (file:File {repo_name: $repo_name})" in GRAPH_QUERY
    assert "Function {repo_name: $repo_name}" in GRAPH_QUERY
    assert "(m {repo_name: $repo_name})" in GRAPH_QUERY
    assert "\nMATCH (n)\n" not in GRAPH_QUERY


def test_chunk_data_uses_bounded_slices() -> None:
    chunks = list(chunk_data(list(range(205))))

    assert [len(chunk) for chunk in chunks] == [100, 100, 5]
    assert [item for chunk in chunks for item in chunk] == list(range(205))


def test_three_pass_write_receives_repository_scope() -> None:
    driver, session, transaction = _mock_driver()
    parsed_data = [
        {
            "file_path": "src/example.py",
            "defined_functions": ["example"],
            "outgoing_calls": ["external_call"],
        }
    ]

    with (
        patch("app.db.graph_ops.get_neo4j_driver", return_value=driver),
        patch(
            "app.db.graph_ops.generate_embeddings",
            side_effect=_fake_embeddings,
        ) as embed_batch,
        patch(
            "app.db.graph_ops.run_leiden_clustering",
            new=AsyncMock(),
        ) as cluster_graph,
    ):
        asyncio.run(
            save_parsed_ast_to_neo4j(
                parsed_data,
                repo_name="owner/repository-a",
                replace_existing=True,
            )
        )

    assert session.execute_write.await_count == 5
    assert transaction.run.await_count == 5
    expected_queries = [
        DELETE_REPOSITORY_QUERY,
        MERGE_FILES_QUERY,
        MERGE_FUNCTIONS_QUERY,
        MERGE_CALLS_QUERY,
        TAG_EXTERNAL_FUNCTIONS_QUERY,
    ]
    assert [
        call.args[0] for call in transaction.run.await_args_list
    ] == expected_queries
    assert transaction.run.await_args_list[1].kwargs["batch"] == [
        {"path": "src/example.py"}
    ]
    assert transaction.run.await_args_list[2].kwargs["batch"] == [
        {
            "name": "example",
            "file_path": "src/example.py",
            "embedding": [0.1, 0.2, 0.3],
        }
    ]
    assert transaction.run.await_args_list[3].kwargs["batch"] == [
        {
            "caller_name": "example",
            "target_name": "external_call",
            "file_path": "src/example.py",
        }
    ]
    for call in transaction.run.await_args_list:
        assert call.kwargs["repo_name"] == "owner/repository-a"
        assert "$repo_name" in call.args[0]
    embed_batch.assert_awaited_once_with(
        ["Function: example\nFile: src/example.py"]
    )
    cluster_graph.assert_awaited_once_with("owner/repository-a")


def test_large_repository_uses_one_transaction_per_micro_batch() -> None:
    driver, session, transaction = _mock_driver()
    parsed_data = [
        {
            "file_path": f"src/file_{index}.py",
            "defined_functions": [f"function_{index}"],
            "outgoing_calls": [],
        }
        for index in range(205)
    ]

    with (
        patch("app.db.graph_ops.get_neo4j_driver", return_value=driver),
        patch(
            "app.db.graph_ops.generate_embeddings",
            side_effect=_fake_embeddings,
        ) as embed_batch,
        patch(
            "app.db.graph_ops.run_leiden_clustering",
            new=AsyncMock(),
        ) as cluster_graph,
    ):
        asyncio.run(
            save_parsed_ast_to_neo4j(
                parsed_data,
                repo_name="owner/large-repository",
            )
        )

    # Three file chunks, three function chunks, no call chunks, and one tag pass.
    assert session.execute_write.await_count == 7
    batch_calls = [
        call
        for call in transaction.run.await_args_list
        if "batch" in call.kwargs
    ]
    assert [len(call.kwargs["batch"]) for call in batch_calls] == [
        100,
        100,
        5,
        100,
        100,
        5,
    ]
    assert all(len(call.kwargs["batch"]) <= 100 for call in batch_calls)
    assert [
        len(call.args[0]) for call in embed_batch.await_args_list
    ] == [100, 100, 5]
    cluster_graph.assert_awaited_once_with("owner/large-repository")


def test_external_postprocessing_remains_repository_scoped() -> None:
    assert "SET fn:ExternalFunction" in TAG_EXTERNAL_FUNCTIONS_QUERY
    assert "fn.is_external = true" in TAG_EXTERNAL_FUNCTIONS_QUERY
    assert "$repo_name" in TAG_EXTERNAL_FUNCTIONS_QUERY
