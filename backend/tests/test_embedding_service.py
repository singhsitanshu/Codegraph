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
