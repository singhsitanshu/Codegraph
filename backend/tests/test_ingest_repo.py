"""Focused tests for repository URL parsing and on-demand ingestion."""

import asyncio
import io
import json
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from app.main import app
from app.services.github_service import download_and_extract_repo
from app.services.graph_ingestion import IngestionProgress
from app.services.parser_service import (
    IdentifiedFile,
    ParsedFileProgress,
    ParsedSource,
)
from app.services.source_discovery import discover_repository_source_files
from app.utils.repository import GitHubRepository


def _fake_download(extracted_root: Path, released: list[tuple[str, str]]):
    """Stand in for the download scope and record when it is released."""

    @asynccontextmanager
    async def download(owner: str, name: str):
        try:
            yield extracted_root
        finally:
            released.append((owner, name))

    return download


def test_parse_github_repository_url() -> None:
    assert GitHubRepository.from_url(
        " https://github.com/psf/requests.git/ "
    ) == GitHubRepository(owner="psf", name="requests")


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/psf/requests",
        "https://github.com/psf",
        "https://github.com/psf/requests/tree/main",
    ],
)
def test_parse_github_repository_url_rejects_non_repository_urls(url: str) -> None:
    with pytest.raises(ValueError):
        GitHubRepository.from_url(url)


def test_repository_discovery_includes_every_supported_language(
    tmp_path: Path,
) -> None:
    supported_names = {
        "module.py",
        "client.js",
        "component.jsx",
        "types.ts",
        "view.tsx",
        "server.go",
        "Client.java",
    }
    for file_name in [*supported_names, "README.md"]:
        (tmp_path / file_name).write_text("", encoding="utf-8")

    discovered = discover_repository_source_files(tmp_path)

    assert {Path(file_path).name for file_path in discovered} == supported_names


def test_ingest_repository_uses_relative_paths_and_always_cleans_up(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "downloaded-root"
    source_path = repository_root / "src" / "example.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("def example():\n    return 1\n", encoding="utf-8")

    parsed_source = ParsedSource(
        file_path=str(source_path),
        language="python",
        defined_classes=(),
        functions=(),
        declarations=(),
        unattributed_calls=(),
        outgoing_calls=(),
    )
    released: list[tuple[str, str]] = []
    save_calls = []

    async def parse_with_progress(_file_paths: list[str]):
        yield ParsedFileProgress(
            index=0,
            processed=1,
            total=1,
            source_tokens=23,
            result=parsed_source,
        )

    async def save_with_progress(*args, **kwargs):
        save_calls.append((args, kwargs))
        yield IngestionProgress("Pass 1: Creating Files...", 86)
        yield IngestionProgress("Pass 2: Creating Functions...", 90)
        yield IngestionProgress("Pass 3: Mapping Dependencies...", 94)
        yield IngestionProgress(
            "Detecting architectural communities...",
            97,
        )
        yield IngestionProgress(
            "Labeling architectural communities...",
            98,
        )
        yield IngestionProgress("Completing transaction...", 99)

    with (
        patch(
            "app.services.repository_ingestion.download_and_extract_repo",
            new=_fake_download(repository_root, released),
        ),
        patch(
            "app.services.repository_ingestion.parse_changed_files_with_progress",
            new=parse_with_progress,
        ),
        patch(
            "app.services.repository_ingestion.ingest_identified_files_with_progress",
            new=save_with_progress,
        ),
    ):
        response = TestClient(app).post(
            "/api/ingest-repo",
            json={"url": "https://github.com/psf/requests"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    progress_records = [
        json.loads(line) for line in response.text.splitlines()
    ]
    assert [record["progress"] for record in progress_records] == [
        10,
        20,
        80,
        85,
        86,
        90,
        94,
        97,
        98,
        99,
        100,
    ]
    assert progress_records[-1] == {
        "status": "Repository ingestion complete.",
        "progress": 100,
        "repo_name": "psf/requests",
        "total_repo_tokens": 23,
    }
    assert save_calls == [
        (
            (
                [
                    IdentifiedFile(
                        repository="psf/requests",
                        file_path="src/example.py",
                        language="python",
                        functions=(),
                    )
                ],
            ),
            {
                "repo_name": "psf/requests",
                "replace_existing": True,
                "total_repo_tokens": 23,
            },
        )
    ]
    assert released == [("psf", "requests")]


def test_ingest_repository_rejects_non_github_url() -> None:
    download = AsyncMock()
    with patch("app.services.repository_ingestion.download_and_extract_repo", new=download):
        response = TestClient(app).post(
            "/api/ingest-repo",
            json={"url": "https://example.com/psf/requests"},
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "url"]
    download.assert_not_awaited()


def test_full_ingest_does_not_replace_graph_after_parse_failure(tmp_path: Path) -> None:
    source_path = tmp_path / "broken.py"
    source_path.write_text("def f(): pass\n", encoding="utf-8")

    async def failed_parse(_paths: list[str]):
        yield ParsedFileProgress(
            index=0, processed=1, total=1, source_tokens=0, result=None
        )

    save = Mock()
    released: list[tuple[str, str]] = []
    with (
        patch("app.services.repository_ingestion.download_and_extract_repo", new=_fake_download(tmp_path, released)),
        patch("app.services.repository_ingestion.parse_changed_files_with_progress", new=failed_parse),
        patch("app.services.repository_ingestion.ingest_identified_files_with_progress", new=save),
    ):
        response = TestClient(app).post(
            "/api/ingest-repo", json={"url": "https://github.com/psf/requests"}
        )

    records = [json.loads(line) for line in response.text.splitlines()]
    assert records[-1]["status"] == "Repository ingestion failed."
    assert "could not be parsed" in records[-1]["error"]
    save.assert_not_called()
    assert released == [("psf", "requests")]


def test_neo4j_failure_ends_the_stream_with_a_failure_record(tmp_path: Path) -> None:
    source_path = tmp_path / "app.py"
    source_path.write_text("def f():\n    pass\n", encoding="utf-8")
    parsed_source = ParsedSource(
        file_path=str(source_path),
        language="python",
        defined_classes=(),
        functions=(),
        declarations=(),
        unattributed_calls=(),
        outgoing_calls=(),
    )

    async def parse(_paths: list[str]):
        yield ParsedFileProgress(
            index=0, processed=1, total=1, source_tokens=4, result=parsed_source
        )

    async def unavailable_database(*_args, **_kwargs):
        yield IngestionProgress("Pass 1: Creating Files...", 86)
        raise ServiceUnavailable("connection refused")

    released: list[tuple[str, str]] = []
    with (
        patch(
            "app.services.repository_ingestion.download_and_extract_repo",
            new=_fake_download(tmp_path, released),
        ),
        patch(
            "app.services.repository_ingestion.parse_changed_files_with_progress",
            new=parse,
        ),
        patch(
            "app.services.repository_ingestion.ingest_identified_files_with_progress",
            new=unavailable_database,
        ),
    ):
        response = TestClient(app).post(
            "/api/ingest-repo", json={"url": "https://github.com/psf/requests"}
        )

    records = [json.loads(line) for line in response.text.splitlines()]
    assert records[-1] == {
        "status": "Repository ingestion failed.",
        "progress": 86,
        "error": "Neo4j is unavailable during repository ingestion",
    }
    assert released == [("psf", "requests")]


def _archive_client(*entries: tuple[str, str]) -> MagicMock:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w") as archive:
        for name, content in entries:
            archive.writestr(name, content)

    archive_response = Mock(content=archive_buffer.getvalue())
    archive_response.raise_for_status = Mock()
    client = MagicMock()
    client.get = AsyncMock(return_value=archive_response)
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)
    return client_context


def test_downloaded_repository_lives_for_the_download_scope() -> None:
    client_context = _archive_client(
        ("psf-requests-sha/src/example.py", "def example(): pass\n")
    )

    async def download() -> Path:
        async with download_and_extract_repo("psf", "requests") as extracted_root:
            assert (extracted_root / "src" / "example.py").is_file()
            return extracted_root

    with patch(
        "app.services.github_service.httpx.AsyncClient",
        return_value=client_context,
    ):
        extracted_root = asyncio.run(download())

    client = client_context.__aenter__.return_value
    client.get.assert_awaited_once_with(
        "https://api.github.com/repos/psf/requests/zipball",
    )
    assert not extracted_root.parent.exists()


def test_downloaded_repository_is_removed_when_the_scope_fails() -> None:
    client_context = _archive_client(
        ("psf-requests-sha/src/example.py", "def example(): pass\n")
    )
    extracted_roots: list[Path] = []

    async def download() -> None:
        async with download_and_extract_repo("psf", "requests") as extracted_root:
            extracted_roots.append(extracted_root)
            raise RuntimeError("ingestion failed")

    with (
        patch(
            "app.services.github_service.httpx.AsyncClient",
            return_value=client_context,
        ),
        pytest.raises(RuntimeError),
    ):
        asyncio.run(download())

    assert not extracted_roots[0].parent.exists()
