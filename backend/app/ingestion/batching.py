"""Bounded slicing for work sent to external systems in batches."""

from collections.abc import Iterator
from typing import TypeVar


BatchItem = TypeVar("BatchItem")


def chunk_data(
    data_list: list[BatchItem],
    chunk_size: int,
) -> Iterator[list[BatchItem]]:
    """Yield consecutive slices of at most ``chunk_size`` items."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    for index in range(0, len(data_list), chunk_size):
        yield data_list[index : index + chunk_size]
