"""Unit coverage for repository-scoped Neo4j writes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.graph_ops import save_parsed_ast_to_neo4j


def test_every_graph_write_receives_repository_scope() -> None:
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
        asyncio.run(
            save_parsed_ast_to_neo4j(
                [
                    {
                        "file_path": "src/example.py",
                        "defined_functions": ["example"],
                        "outgoing_calls": ["external_call"],
                    }
                ],
                repo_name="owner/repository-a",
                replace_existing=True,
            )
        )

    assert transaction.run.await_count == 5
    assert "DETACH DELETE node" in transaction.run.await_args_list[0].args[0]
    for call in transaction.run.await_args_list:
        assert call.kwargs["repo_name"] == "owner/repository-a"
        assert "$repo_name" in call.args[0]
