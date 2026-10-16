"""Unit tests for batched OpenAI code embeddings."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.embedding_service import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    generate_embedding,
    generate_embeddings,
)
from app.config import settings


@pytest.fixture(autouse=True)
def isolated_embedding_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_CACHE_PATH", str(tmp_path / "embeddings.sqlite3"))


def _embedding(value: float) -> list[float]:
    return [value] * EMBEDDING_DIMENSIONS


def test_generate_embeddings_batches_and_restores_response_order() -> None:
    client = MagicMock()
    client.embeddings.create = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=_embedding(0.2)),
                SimpleNamespace(index=0, embedding=_embedding(0.1)),
            ]
        )
    )

    with patch(
        "app.services.embedding_service._get_embedding_client",
        return_value=client,
    ):
        result = asyncio.run(generate_embeddings([" first ", "second"]))

    assert result[0][0] == 0.1
    assert result[1][0] == 0.2
    client.embeddings.create.assert_awaited_once_with(
        input=["first", "second"],
        model=EMBEDDING_MODEL,
    )


def test_generate_embedding_returns_the_single_vector() -> None:
    vector = _embedding(0.3)
    with patch(
        "app.services.embedding_service.generate_embeddings",
        new=AsyncMock(return_value=[vector]),
    ) as generate_batch:
        result = asyncio.run(generate_embedding("payment processing"))

    assert result == vector
    generate_batch.assert_awaited_once_with(["payment processing"])


def test_generate_embeddings_rejects_blank_input() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        asyncio.run(generate_embeddings(["  "]))


def _client_for_vectors(values):
    client = MagicMock()
    client.embeddings.create = AsyncMock(return_value=SimpleNamespace(data=[
        SimpleNamespace(index=i, embedding=_embedding(value)) for i, value in enumerate(values)
    ]))
    return client


def test_identical_inputs_are_embedded_once_and_expanded_in_order():
    client = _client_for_vectors([0.1, 0.2])
    with patch("app.services.embedding_service._get_embedding_client", return_value=client):
        result = asyncio.run(generate_embeddings(["same", " other ", " same "]))
    assert [vector[0] for vector in result] == [0.1, 0.2, 0.1]
    client.embeddings.create.assert_awaited_once_with(input=["same", "other"], model=EMBEDDING_MODEL)


def test_cached_vectors_survive_new_event_loop_and_only_missing_inputs_are_requested():
    client = _client_for_vectors([0.1])
    with patch("app.services.embedding_service._get_embedding_client", return_value=client):
        first = asyncio.run(generate_embeddings(["existing"]))
        repeated = asyncio.run(generate_embeddings(["existing"]))
        assert repeated == first
        assert client.embeddings.create.await_count == 1
        client.embeddings.create.return_value = SimpleNamespace(data=[SimpleNamespace(index=0, embedding=_embedding(0.2))])
        result = asyncio.run(generate_embeddings(["existing", "new", "existing"]))
    assert [vector[0] for vector in result] == [0.1, 0.2, 0.1]
    assert client.embeddings.create.await_args.kwargs["input"] == ["new"]


def test_model_change_does_not_reuse_old_model_vectors():
    client = _client_for_vectors([0.1])
    with patch("app.services.embedding_service._get_embedding_client", return_value=client):
        asyncio.run(generate_embeddings(["same"]))
        with patch("app.services.embedding_service.EMBEDDING_MODEL", "other-model"):
            asyncio.run(generate_embeddings(["same"]))
    assert client.embeddings.create.await_count == 2


@pytest.mark.parametrize("data", [
    [SimpleNamespace(index=0, embedding=[0.1])],
    [SimpleNamespace(index=1, embedding=_embedding(0.1))],
])
def test_invalid_api_vectors_are_not_cached(data):
    client = _client_for_vectors([0.1])
    client.embeddings.create.return_value = SimpleNamespace(data=data)
    with patch("app.services.embedding_service._get_embedding_client", return_value=client):
        with pytest.raises(RuntimeError, match="unexpected embedding"):
            asyncio.run(generate_embeddings(["same"]))
        client.embeddings.create.return_value = SimpleNamespace(data=[SimpleNamespace(index=0, embedding=_embedding(0.1))])
        asyncio.run(generate_embeddings(["same"]))
    assert client.embeddings.create.await_count == 2


def test_unavailable_cache_does_not_prevent_embedding_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_CACHE_PATH", str(tmp_path))
    client = _client_for_vectors([0.1])
    with patch("app.services.embedding_service._get_embedding_client", return_value=client):
        result = asyncio.run(generate_embeddings(["same"]))
    assert result == [_embedding(0.1)]
