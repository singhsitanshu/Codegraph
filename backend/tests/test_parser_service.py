"""Fault-tolerance tests for batch source parsing."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter import Language

from app.services.batch_parsing import (
    parse_changed_files,
    parse_changed_files_with_progress,
)
from app.services.languages import LANGUAGES, SUPPORTED_EXTENSIONS, LanguageSpec
from app.services.parse_results import ParsedSource
from app.services.parser_service import CodeParser


@pytest.fixture(autouse=True)
def deterministic_token_counter():
    """Keep parser tests offline while verifying token totals are propagated."""

    with patch("app.services.batch_parsing.count_tokens", return_value=17):
        yield


def _parsed_source(file_path: str) -> ParsedSource:
    return ParsedSource(
        file_path=file_path,
        language="python",
        defined_classes=(),
        functions=(),
        declarations=(),
        unattributed_calls=(),
        outgoing_calls=(),
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


@pytest.mark.parametrize("spec", LANGUAGES, ids=lambda spec: spec.name)
def test_language_spec_node_types_exist_in_its_grammar(spec: LanguageSpec) -> None:
    language = Language(spec.grammar())
    node_types = (
        spec.scope_node_types
        | spec.call_node_types
        | spec.anonymous_function_node_types
        | spec.assigned_function_node_types
        | spec.receiver_method_node_types
    )

    assert node_types == {
        node_type
        for node_type in node_types
        if language.id_for_node_kind(node_type, True)
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

    assert result.file_path == file_path
    assert result.language == SUPPORTED_EXTENSIONS[Path(file_path).suffix]
    assert result.defined_classes == tuple(classes)
    assert result.outgoing_calls == tuple(calls)
    assert [function.name for function in result.functions] == functions
    assert result.declarations == ()
    assert all(
        function.name in function.raw_code for function in result.functions
    )


def test_code_parser_extracts_exact_function_source() -> None:
    source = (
        b"def first(value):\n"
        b"    return value + 1\n\n"
        b"def second():\n"
        b"    return first(2)\n"
    )

    result = asyncio.run(CodeParser().parse_file("module.py", source))

    assert [(function.name, function.raw_code) for function in result.functions] == [
        ("first", "def first(value):\n    return value + 1"),
        ("second", "def second():\n    return first(2)"),
    ]


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

    good_result = _parsed_source(str(good_file))

    async def parse_file(
        _parser: CodeParser,
        file_path: str,
        _source_code: bytes,
    ) -> ParsedSource:
        if file_path == str(bad_file):
            raise file_error
        return good_result

    with patch.object(CodeParser, "parse_file", new=parse_file):
        batch = asyncio.run(
            parse_changed_files([str(good_file), str(bad_file)])
        )

    assert batch.files == [good_result]
    assert batch.source_tokens == 34


def test_failed_parse_still_contributes_to_repository_token_baseline(
    tmp_path: Path,
) -> None:
    good_file = tmp_path / "good.py"
    bad_file = tmp_path / "bad.py"
    good_file.write_bytes(b"def good():\n    return 1\n")
    bad_file.write_bytes(b"def bad():\n    return 2\n")

    async def parse_file(
        _parser: CodeParser,
        file_path: str,
        _source_code: bytes,
    ) -> ParsedSource:
        if file_path == str(bad_file):
            raise RuntimeError("Tree-sitter failure")
        return _parsed_source(file_path)

    async def collect_progress():
        return [
            update
            async for update in parse_changed_files_with_progress(
                [str(good_file), str(bad_file)]
            )
        ]

    with patch.object(CodeParser, "parse_file", new=parse_file):
        updates = asyncio.run(collect_progress())

    assert sum(update.source_tokens for update in updates) == 34
    assert sum(update.result is not None for update in updates) == 1


def test_parse_changed_files_skips_unreadable_file(tmp_path: Path) -> None:
    """A file read failure must not abort parsing of readable neighbors."""

    missing_file = tmp_path / "missing.py"
    good_file = tmp_path / "good.py"
    good_file.write_bytes(b"def good():\n    return 1\n")

    batch = asyncio.run(
        parse_changed_files([str(missing_file), str(good_file)])
    )

    assert len(batch.files) == 1
    assert batch.files[0].file_path == str(good_file)
    assert [function.name for function in batch.files[0].functions] == ["good"]
    assert batch.source_tokens == 17


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
    assert sum(update.source_tokens for update in updates) == 17
    successful_update = next(
        update for update in updates if update.result is not None
    )
    assert successful_update.source_tokens == 17
    failed_update = next(update for update in updates if update.result is None)
    assert failed_update.source_tokens == 0
