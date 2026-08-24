"""Token-counting helpers used by ingestion and Graph-RAG metrics."""

from functools import lru_cache

import tiktoken
from tiktoken.core import Encoding


DEFAULT_TOKEN_MODEL = "gpt-4o"
FALLBACK_ENCODING = "cl100k_base"


@lru_cache(maxsize=16)
def _encoding_for_model(model: str) -> Encoding:
    """Resolve and cache a model encoding with a stable fallback."""

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding(FALLBACK_ENCODING)


def count_tokens(text: str, model: str = DEFAULT_TOKEN_MODEL) -> int:
    """Return the number of tokens in ``text`` for the requested model."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError("model must not be blank")
    return len(_encoding_for_model(normalized_model).encode(text))
