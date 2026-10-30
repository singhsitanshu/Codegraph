"""Focused tests for repository URL parsing and on-demand ingestion."""

import asyncio
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import _discover_repository_source_files, app
from app.services.github_service import (
    cleanup_downloaded_repo,
    download_and_extract_repo,
)
from app.services.parser_service import (
    IdentifiedFile,
    ParsedFileProgress,
    ParsedSource,
)
from app.db.graph_ops import DatabaseWriteProgress
from app.utils.repository import GitHubRepository


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

    discovered = _discover_repository_source_files(str(tmp_path))

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
    cleanup = Mock()
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
        yield DatabaseWriteProgress("Pass 1: Creating Files...", 86)
        yield DatabaseWriteProgress("Pass 2: Creating Functions...", 90)
        yield DatabaseWriteProgress("Pass 3: Mapping Dependencies...", 94)
        yield DatabaseWriteProgress(
            "Detecting architectural communities...",
            97,
        )
        yield DatabaseWriteProgress(
            "Labeling architectural communities...",
            98,
        )
        yield DatabaseWriteProgress("Completing transaction...", 99)

    with (
        patch(
            "app.main.download_and_extract_repo",
            new=AsyncMock(return_value=str(repository_root)),
        ),
        patch(
            "app.main.parse_changed_files_with_progress",
            new=parse_with_progress,
        ),
        patch(
            "app.main.save_parsed_ast_to_neo4j_with_progress",
            new=save_with_progress,
        ),
        patch("app.main.cleanup_downloaded_repo", new=cleanup),
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
    cleanup.assert_called_once_with(str(repository_root))


def test_ingest_repository_rejects_non_github_url() -> None:
    download = AsyncMock()
    with patch("app.main.download_and_extract_repo", new=download):
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
    with (
        patch("app.main.download_and_extract_repo", new=AsyncMock(return_value=str(tmp_path))),
        patch("app.main.parse_changed_files_with_progress", new=failed_parse),
        patch("app.main.save_parsed_ast_to_neo4j_with_progress", new=save),
        patch("app.main.cleanup_downloaded_repo"),
    ):
        response = TestClient(app).post(
            "/api/ingest-repo", json={"url": "https://github.com/psf/requests"}
        )

    records = [json.loads(line) for line in response.text.splitlines()]
    assert records[-1]["status"] == "Repository ingestion failed."
    assert "could not be parsed" in records[-1]["error"]
    save.assert_not_called()


def test_downloaded_repository_lives_until_explicit_cleanup() -> None:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w") as archive:
        archive.writestr("psf-requests-sha/src/example.py", "def example(): pass\n")

    archive_response = Mock(content=archive_buffer.getvalue())
    archive_response.raise_for_status = Mock()
    client = MagicMock()
    client.get = AsyncMock(return_value=archive_response)
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.github_service.httpx.AsyncClient",
        return_value=client_context,
    ):
        extracted_root = asyncio.run(
            download_and_extract_repo("psf", "requests")
        )

    extracted_path = Path(extracted_root)
    temporary_parent = extracted_path.parent
    try:
        assert (extracted_path / "src" / "example.py").is_file()
        client.get.assert_awaited_once_with(
            "https://api.github.com/repos/psf/requests/zipball",
        )
    finally:
        cleanup_downloaded_repo(extracted_root)

    assert not temporary_parent.exists()
