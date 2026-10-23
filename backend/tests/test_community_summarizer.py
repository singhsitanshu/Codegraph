"""Structured community labels, batching, and atomic publication."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.services.community_summarizer import (
    COMMUNITY_LABEL_BATCH_SIZE,
    COMMUNITY_LABEL_MODEL,
    MAX_CONCURRENT_COMMUNITY_LABELS,
    DELETE_COMMUNITIES_QUERY,
    FETCH_COMMUNITIES_QUERY,
    STORE_COMMUNITIES_QUERY,
    UNGROUP_SMALL_COMMUNITIES_QUERY,
    UNGROUPED_COMMUNITY_ID,
    CommunityLabel,
    _generate_community_labels,
    label_and_store_communities,
)


def _async_context(value):
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=value)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


def _driver_for_records(records):
    result = MagicMock()
    result.data = AsyncMock(return_value=records)
    result.consume = AsyncMock()
    session = MagicMock()
    session.run = AsyncMock(return_value=result)
    transaction = MagicMock()
    transaction.run = AsyncMock(return_value=result)

    async def write(callback):
        await callback(transaction)

    session.execute_write = AsyncMock(side_effect=write)
    driver = MagicMock()
    driver.session.return_value = _async_context(session)
    return driver, session, transaction


def test_label_and_store_communities_replaces_repository_labels_atomically():
    records = [
        dict(comm_id=2, func_names=["get", "post", "put"], file_paths=["api.py"], function_count=3),
        dict(comm_id=7, func_names=["extract_cookies", "store", "load"], file_paths=["cookies.py"], function_count=3),
    ]
    driver, session, transaction = _driver_for_records(records)
    labels = [
        dict(id=2, name="HTTP Session Management", description="Coordinates HTTP requests."),
        dict(id=7, name="Cookie Handling", description="Extracts cookies."),
    ]
    with (
        patch("app.services.community_summarizer.get_neo4j_driver", return_value=driver),
        patch("app.services.community_summarizer._generate_community_labels", new=AsyncMock(return_value=labels)) as generate,
    ):
        communities = asyncio.run(label_and_store_communities(" owner/repository "))
    assert communities == labels
    generate.assert_awaited_once_with(records)
    session.run.assert_awaited_once_with(FETCH_COMMUNITIES_QUERY, repo_name="owner/repository")
    assert transaction.run.await_args_list == [
        call(DELETE_COMMUNITIES_QUERY, repo_name="owner/repository"),
        call(STORE_COMMUNITIES_QUERY, repo_name="owner/repository", communities=communities),
    ]
    session.execute_write.assert_awaited_once()


def test_generate_community_labels_uses_structured_ids_and_restores_order():
    parsed = SimpleNamespace(
        community_7=CommunityLabel(name="Cookies", description="Manages cookies."),
        community_2=CommunityLabel(name="Transport", description="Sends HTTP requests."),
    )
    client = MagicMock()
    client.beta.chat.completions.parse = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=None))]
    ))
    records = [dict(comm_id=2, func_names=["send"], file_paths=["adapters.py"]), dict(comm_id=7, func_names=["cookies"], file_paths=["cookies.py"])]
    with patch("app.services.community_summarizer._get_community_label_client", return_value=client):
        labels = asyncio.run(_generate_community_labels(records))
    assert [label["id"] for label in labels] == [2, 7]
    kwargs = client.beta.chat.completions.parse.await_args.kwargs
    assert kwargs["model"] == COMMUNITY_LABEL_MODEL
    assert set(kwargs["response_format"].model_fields) == {"community_2", "community_7"}
    assert "adapters.py" in kwargs["messages"][1]["content"]


@pytest.mark.parametrize("ids", [[2], [2, 2], [2, 99]])
def test_label_response_rejects_missing_duplicate_or_foreign_ids(ids):
    parsed = SimpleNamespace(**{f"community_{i}": CommunityLabel(name="Name", description="Description") for i in ids})
    client = MagicMock()
    client.beta.chat.completions.parse = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=None))]
    ))
    with patch("app.services.community_summarizer._get_community_label_client", return_value=client):
        with pytest.raises(RuntimeError, match="missing a required key"):
            asyncio.run(_generate_community_labels([dict(comm_id=2), dict(comm_id=7)]))


def test_label_and_store_communities_rejects_blank_repository():
    with pytest.raises(ValueError, match="repo_name must not be blank"):
        asyncio.run(label_and_store_communities("  "))


def test_small_communities_are_grouped_without_model_requests():
    records = [
        dict(comm_id=1, function_count=5, func_names=["a"], file_paths=["a.py"]),
        dict(comm_id=4, function_count=2, func_names=["b", "c"], file_paths=["b.py"]),
        dict(comm_id=9, function_count=1, func_names=["d"], file_paths=["d.py"]),
    ]
    driver, _, transaction = _driver_for_records(records)
    labels = [dict(id=1, name="Core", description="Core logic.")]
    with (
        patch("app.services.community_summarizer.get_neo4j_driver", return_value=driver),
        patch("app.services.community_summarizer._generate_community_labels", new=AsyncMock(return_value=labels)) as generate,
    ):
        communities = asyncio.run(label_and_store_communities("owner/repo"))
    generate.assert_awaited_once_with([records[0]])
    assert [(community["id"], community["name"]) for community in communities] == [
        (1, "Core"),
        (UNGROUPED_COMMUNITY_ID, "Ungrouped"),
    ]
    assert transaction.run.await_args_list == [
        call(DELETE_COMMUNITIES_QUERY, repo_name="owner/repo"),
        call(
            UNGROUP_SMALL_COMMUNITIES_QUERY,
            repo_name="owner/repo",
            community_ids=[4, 9],
            ungrouped_id=UNGROUPED_COMMUNITY_ID,
        ),
        call(STORE_COMMUNITIES_QUERY, repo_name="owner/repo", communities=communities),
    ]


def test_community_requests_are_batched_bounded_and_keep_order():
    count = COMMUNITY_LABEL_BATCH_SIZE * MAX_CONCURRENT_COMMUNITY_LABELS + 3
    records = [dict(comm_id=i, function_count=3, func_names=[str(i)], file_paths=["a.py"]) for i in range(count)]
    driver, _, _ = _driver_for_records(records)
    active = peak = 0

    async def generate(batch):
        nonlocal active, peak
        assert len(batch) <= COMMUNITY_LABEL_BATCH_SIZE
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return [dict(id=r["comm_id"], name=str(r["comm_id"]), description="Community") for r in batch]

    with (
        patch("app.services.community_summarizer.get_neo4j_driver", return_value=driver),
        patch("app.services.community_summarizer._generate_community_labels", side_effect=generate) as generated,
    ):
        labels = asyncio.run(label_and_store_communities("owner/repo"))
    assert peak == MAX_CONCURRENT_COMMUNITY_LABELS
    assert generated.await_count == 5
    assert [label["name"] for label in labels] == [str(i) for i in range(count)]


def test_label_failure_cancels_other_requests_without_replacing_stored_labels():
    count = COMMUNITY_LABEL_BATCH_SIZE * MAX_CONCURRENT_COMMUNITY_LABELS
    records = [dict(comm_id=i, function_count=3, func_names=[str(i)], file_paths=["a.py"]) for i in range(count)]
    driver, session, _ = _driver_for_records(records)
    active = 0

    async def generate(batch):
        nonlocal active
        active += 1
        try:
            await asyncio.sleep(0)
            if batch[0]["comm_id"] == 0:
                raise RuntimeError("label request failed")
            await asyncio.Event().wait()
        finally:
            active -= 1

    with (
        patch("app.services.community_summarizer.get_neo4j_driver", return_value=driver),
        patch("app.services.community_summarizer._generate_community_labels", side_effect=generate),
    ):
        with pytest.raises(RuntimeError, match="label request failed"):
            asyncio.run(label_and_store_communities("owner/repo"))
    assert active == 0
    session.execute_write.assert_not_awaited()
