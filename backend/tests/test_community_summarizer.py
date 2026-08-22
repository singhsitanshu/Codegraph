"""Tests for LLM-generated, repository-scoped community labels."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.services.community_summarizer import (
    COMMUNITY_LABEL_MODEL,
    DELETE_COMMUNITIES_QUERY,
    FETCH_COMMUNITIES_QUERY,
    STORE_COMMUNITIES_QUERY,
    CommunityLabel,
    _generate_community_label,
    label_and_store_communities,
)


def _async_context(value: object) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=value)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


def test_label_and_store_communities_replaces_repository_labels_atomically() -> None:
    read_result = MagicMock()
    read_result.data = AsyncMock(
        return_value=[
            {
                "comm_id": 2,
                "func_names": ["get", "post", "request"],
                "file_paths": ["requests/api.py", "requests/sessions.py"],
            },
            {
                "comm_id": 7,
                "func_names": ["extract_cookies"],
                "file_paths": ["requests/cookies.py"],
            },
        ]
    )
    read_session = MagicMock()
    read_session.run = AsyncMock(return_value=read_result)

    transaction = MagicMock()
    transaction_result = MagicMock()
    transaction_result.consume = AsyncMock()
    transaction.run = AsyncMock(return_value=transaction_result)
    write_session = MagicMock()

    async def execute_write(callback):
        await callback(transaction)

    write_session.execute_write = AsyncMock(side_effect=execute_write)
    driver = MagicMock()
    driver.session.side_effect = [
        _async_context(read_session),
        _async_context(write_session),
    ]
    generate_label = AsyncMock(
        side_effect=[
            CommunityLabel(
                name="HTTP Session Management",
                description="Coordinates HTTP requests and persistent sessions.",
            ),
            CommunityLabel(
                name="Cookie Handling",
                description="Extracts and manages HTTP cookie state.",
            ),
        ]
    )

    with (
        patch(
            "app.services.community_summarizer.get_neo4j_driver",
            return_value=driver,
        ),
        patch(
            "app.services.community_summarizer._generate_community_label",
            new=generate_label,
        ),
    ):
        communities = asyncio.run(
            label_and_store_communities(" owner/repository ")
        )

    assert [community["name"] for community in communities] == [
        "HTTP Session Management",
        "Cookie Handling",
    ]
    read_session.run.assert_awaited_once_with(
        FETCH_COMMUNITIES_QUERY,
        repo_name="owner/repository",
    )
    assert transaction.run.await_args_list == [
        call(DELETE_COMMUNITIES_QUERY, repo_name="owner/repository"),
        call(
            STORE_COMMUNITIES_QUERY,
            repo_name="owner/repository",
            communities=communities,
        ),
    ]
    write_session.execute_write.assert_awaited_once()


def test_generate_community_label_uses_structured_output() -> None:
    parsed = CommunityLabel(
        name="Transport Adapters",
        description="Connects requests to HTTP transport implementations.",
    )
    message = MagicMock(parsed=parsed, refusal=None)
    completion = MagicMock(choices=[MagicMock(message=message)])
    parse = AsyncMock(return_value=completion)
    client = MagicMock()
    client.beta.chat.completions.parse = parse

    with patch(
        "app.services.community_summarizer._get_community_label_client",
        return_value=client,
    ):
        result = asyncio.run(
            _generate_community_label(
                ["send", "build_response"],
                ["requests/adapters.py"],
            )
        )

    assert result == parsed
    assert parse.await_args.kwargs["model"] == COMMUNITY_LABEL_MODEL
    assert parse.await_args.kwargs["response_format"] is CommunityLabel
    assert "requests/adapters.py" in parse.await_args.kwargs["messages"][1][
        "content"
    ]


def test_label_and_store_communities_rejects_blank_repository() -> None:
    with pytest.raises(ValueError, match="repo_name must not be blank"):
        asyncio.run(label_and_store_communities("  "))
