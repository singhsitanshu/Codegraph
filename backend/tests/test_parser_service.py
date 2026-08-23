"""Fault-tolerance tests for batch source parsing."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.parser_service import (
    SUPPORTED_EXTENSIONS,
    CodeParser,
    parse_changed_files,
    parse_changed_files_with_progress,
)


def test_supported_extension_mapping_covers_all_requested_languages() -> None:
    assert SUPPORTED_EXTENSIONS == {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".go": "go",
        ".java": "java",
    }


@pytest.mark.parametrize(
    ("file_path", "source", "functions", "calls", "classes"),
    [
        (
            "module.py",
            b"class Client:\n"
            b"    def send(self):\n"
            b"        api.call()\n"
            b"def top():\n"
            b"    send()\n",
            ["send", "top"],
            ["call", "send"],
            ["Client"],
        ),
        (
            "module.js",
            b"class Client { send() { api.call() } }\n"
            b"const build = () => send();\n"
            b"function top() { build(); }\n",
            ["send", "build", "top"],
            ["call", "send", "build"],
            ["Client"],
        ),
        (
            "component.jsx",
            b"const Button = () => <button />;\n"
            b"function render() { mount(Button()); }\n",
            ["Button", "render"],
            ["mount", "Button"],
            [],
        ),
        (
            "module.ts",
            b"abstract class Client { send(): void { api.call(); } }\n"
            b"const build = (): void => send();\n"
            b"function top(): void { build(); }\n",
            ["send", "build", "top"],
            ["call", "send", "build"],
            ["Client"],
        ),
        (
            "component.tsx",
            b"const Panel = (): JSX.Element => <div />;\n"
            b"function render(): void { mount(Panel()); }\n",
            ["Panel", "render"],
            ["mount", "Panel"],
            [],
        ),
        (
            "module.go",
            b"package demo\n"
            b"type Client struct{}\n"
            b"func Top() { helper(); api.Call() }\n"
            b"func (c *Client) Send() { Top() }\n",
            ["Top", "Send"],
            ["helper", "Call", "Top"],
            ["Client"],
        ),
        (
            "Client.java",
            b"package demo;\n"
            b"class Client {\n"
            b"  Client() { initialize(); }\n"
            b"  void send() { api.call(); helper(); }\n"
            b"}\n",
            ["Client", "send"],
            ["initialize", "call", "helper"],
            ["Client"],
        ),
    ],
)
def test_code_parser_normalizes_supported_languages(
    file_path: str,
    source: bytes,
    functions: list[str],
    calls: list[str],
    classes: list[str],
) -> None:
    async def parse():
        return await CodeParser().parse_file(file_path, source)

    result = asyncio.run(parse())

    assert result == {
        "file_path": file_path,
        "defined_classes": classes,
        "defined_functions": functions,
        "outgoing_calls": calls,
    }


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


def test_parse_progress_advances_for_every_file(tmp_path: Path) -> None:
    """Skipped files still count toward deterministic batch progress."""

    missing_file = tmp_path / "missing.py"
    good_file = tmp_path / "good.py"
    good_file.write_bytes(b"def good():\n    return 1\n")

    async def collect_progress():
        return [
            update
            async for update in parse_changed_files_with_progress(
                [str(missing_file), str(good_file)]
            )
        ]

    updates = asyncio.run(collect_progress())

    assert [update.processed for update in updates] == [1, 2]
    assert all(update.total == 2 for update in updates)
    assert sum(update.result is not None for update in updates) == 1
