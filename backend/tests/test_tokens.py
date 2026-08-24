"""Tests for deterministic token-counting behavior."""

from unittest.mock import MagicMock, patch

import pytest

from app.utils import tokens


def test_count_tokens_uses_requested_model_encoding() -> None:
    encoding = MagicMock()
    encoding.encode.return_value = [1, 2, 3]
    tokens._encoding_for_model.cache_clear()

    with patch.object(
        tokens.tiktoken,
        "encoding_for_model",
        return_value=encoding,
    ) as encoding_for_model:
        assert tokens.count_tokens("hello world", "gpt-4o") == 3

    encoding_for_model.assert_called_once_with("gpt-4o")
    encoding.encode.assert_called_once_with("hello world")
    tokens._encoding_for_model.cache_clear()


def test_count_tokens_falls_back_for_unknown_model() -> None:
    encoding = MagicMock()
    encoding.encode.return_value = [1]
    tokens._encoding_for_model.cache_clear()

    with (
        patch.object(
            tokens.tiktoken,
            "encoding_for_model",
            side_effect=KeyError("unknown model"),
        ),
        patch.object(
            tokens.tiktoken,
            "get_encoding",
            return_value=encoding,
        ) as get_encoding,
    ):
        assert tokens.count_tokens("fallback", "future-model") == 1

    get_encoding.assert_called_once_with("cl100k_base")
    tokens._encoding_for_model.cache_clear()


def test_count_tokens_validates_inputs() -> None:
    with pytest.raises(TypeError, match="text must be a string"):
        tokens.count_tokens(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="model must not be blank"):
        tokens.count_tokens("text", "  ")
