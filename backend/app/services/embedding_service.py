"""OpenAI embedding utilities for code-graph semantic search."""

import asyncio
import logging
from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings
from app.services.embedding_cache import read_embeddings, write_embeddings


logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_REQUEST_BATCH_SIZE = 512
MAX_CONCURRENT_EMBEDDING_REQUESTS = 4


@lru_cache(maxsize=1)
def _get_embedding_client() -> AsyncOpenAI:
    """Create the async client lazily after configuration is loaded."""

    api_key = settings.OPENAI_API_KEY.strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to generate embeddings")
    return AsyncOpenAI(api_key=api_key)


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed a non-empty text batch in the same order it was supplied."""

    normalized_texts = [text.strip() for text in texts]
    if not normalized_texts:
        return []
    if any(not text for text in normalized_texts):
        raise ValueError("embedding input text must not be blank")

    unique_texts = list(dict.fromkeys(normalized_texts))
    cached = await asyncio.to_thread(
        read_embeddings, unique_texts, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
    )
    missing = [text for text in unique_texts if text not in cached]
    for offset in range(0, len(missing), EMBEDDING_REQUEST_BATCH_SIZE):
        batch = missing[offset:offset + EMBEDDING_REQUEST_BATCH_SIZE]
        response = await _get_embedding_client().embeddings.create(
            input=batch,
            model=EMBEDDING_MODEL,
        )
        ordered_data = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in ordered_data] != list(range(len(batch))):
            raise RuntimeError("OpenAI returned an unexpected embedding count or index")
        embeddings = [list(item.embedding) for item in ordered_data]
        if any(len(embedding) != EMBEDDING_DIMENSIONS for embedding in embeddings):
            raise RuntimeError("OpenAI returned an unexpected embedding dimension")
        generated = dict(zip(batch, embeddings, strict=True))
        cached.update(generated)
        await asyncio.to_thread(
            write_embeddings, generated, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
        )
    logger.info(
        "Embedding inputs: %d definitions, %d unique, %d cached, %d generated with %s",
        len(normalized_texts), len(unique_texts), len(unique_texts) - len(missing),
        len(missing), EMBEDDING_MODEL,
    )
    return [cached[text] for text in normalized_texts]


async def generate_embedding(text: str) -> list[float]:
    """Generate one 1,536-dimensional semantic embedding."""

    return (await generate_embeddings([text]))[0]
