"""OpenAI embedding utilities for code-graph semantic search."""

from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings


EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


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

    response = await _get_embedding_client().embeddings.create(
        input=normalized_texts,
        model=EMBEDDING_MODEL,
    )
    ordered_data = sorted(response.data, key=lambda item: item.index)
    embeddings = [list(item.embedding) for item in ordered_data]
    if len(embeddings) != len(normalized_texts):
        raise RuntimeError("OpenAI returned an unexpected embedding count")
    if any(len(embedding) != EMBEDDING_DIMENSIONS for embedding in embeddings):
        raise RuntimeError("OpenAI returned an unexpected embedding dimension")
    return embeddings


async def generate_embedding(text: str) -> list[float]:
    """Generate one 1,536-dimensional semantic embedding."""

    return (await generate_embeddings([text]))[0]
