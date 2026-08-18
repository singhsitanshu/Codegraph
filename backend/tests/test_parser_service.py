"""Fault-tolerance tests for batch source parsing."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.parser_service import CodeParser, parse_changed_files


@pytest.mark.parametrize(
    "file_error",
    [
        RuntimeError("Tree-sitter failure"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte"),
    ],
)
def test_parse_changed_files_skips_one_parser_failure(
    tmp_path: Path,
    file_error: Exception,
) -> None:
    """A parser failure must not discard other files in the same batch."""

    good_file = tmp_path / "good.py"
    bad_file = tmp_path / "bad.py"
    good_file.write_bytes(b"def good():\n    return 1\n")
    bad_file.write_bytes(b"def bad():\n    return 2\n")

    good_result = {
        "file_path": str(good_file),
        "defined_classes": [],
        "defined_functions": ["good"],
        "outgoing_calls": [],
    }
    async def parse_file(
        _parser: CodeParser,
        file_path: str,
        _source_code: bytes,
    ) -> dict[str, str | list[str]]:
        if file_path == str(bad_file):
            raise file_error
        return good_result

    with patch.object(CodeParser, "parse_file", new=parse_file):
        results = asyncio.run(
            parse_changed_files([str(good_file), str(bad_file)])
        )

    assert results == [good_result]


def test_parse_changed_files_skips_unreadable_file(tmp_path: Path) -> None:
    """A file read failure must not abort parsing of readable neighbors."""

    missing_file = tmp_path / "missing.py"
    good_file = tmp_path / "good.py"
    good_file.write_bytes(b"def good():\n    return 1\n")

    results = asyncio.run(
        parse_changed_files([str(missing_file), str(good_file)])
    )

    assert len(results) == 1
    assert results[0]["file_path"] == str(good_file)
    assert results[0]["defined_functions"] == ["good"]
