"""Local persistent reuse of exact embedding inputs across graph rebuilds."""

import hashlib
import json
import logging
import sqlite3
import struct
from pathlib import Path

from app.config import settings


logger = logging.getLogger(__name__)


def _key(text: str, model: str, dimensions: int) -> str:
    encoded = json.dumps([1, model, dimensions, text], separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _connect() -> sqlite3.Connection:
    path = Path(settings.EMBEDDING_CACHE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS embeddings ("
        "cache_key TEXT PRIMARY KEY, vector BLOB NOT NULL)"
    )
    return connection


def read_embeddings(texts: list[str], model: str, dimensions: int) -> dict[str, list[float]]:
    if not settings.EMBEDDING_CACHE_PATH:
        return {}
    cached = {}
    connection = None
    try:
        connection = _connect()
        keys = {_key(text, model, dimensions): text for text in texts}
        key_list = list(keys)
        for offset in range(0, len(key_list), 500):
            batch = key_list[offset:offset + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                f"SELECT cache_key, vector FROM embeddings WHERE cache_key IN ({placeholders})",
                batch,
            )
            for key, vector in rows:
                if len(vector) == dimensions * 8:
                    cached[keys[key]] = list(struct.unpack(f"<{dimensions}d", vector))
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Embedding cache read unavailable: %s", exc)
    finally:
        if connection is not None:
            connection.close()
    return cached


def write_embeddings(vectors: dict[str, list[float]], model: str, dimensions: int) -> None:
    if not settings.EMBEDDING_CACHE_PATH or not vectors:
        return
    connection = None
    try:
        connection = _connect()
        with connection:
            connection.executemany(
                "INSERT OR REPLACE INTO embeddings (cache_key, vector) VALUES (?, ?)",
                [
                    (_key(text, model, dimensions), struct.pack(f"<{dimensions}d", *vector))
                    for text, vector in vectors.items()
                ],
            )
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Embedding cache write unavailable: %s", exc)
    finally:
        if connection is not None:
            connection.close()
