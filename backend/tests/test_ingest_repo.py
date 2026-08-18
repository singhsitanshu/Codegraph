"""Focused tests for repository URL parsing and on-demand ingestion."""

import asyncio
import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from fastapi.testclient import TestClient

from app.main import _parse_github_repository_url, app
from app.services.github_service import (
    cleanup_downloaded_repo,
    download_and_extract_repo,
)


def test_parse_github_repository_url() -> None:
    assert _parse_github_repository_url(
        "https://github.com/psf/requests.git/"
    ) == ("psf", "requests")


def test_ingest_repository_uses_relative_paths_and_always_cleans_up(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "downloaded-root"
    source_path = repository_root / "src" / "example.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("def example():\n    return 1\n", encoding="utf-8")

    parsed_data = [
        {
            "file_path": str(source_path),
            "defined_functions": ["example"],
            "outgoing_calls": [],
        }
    ]
    cleanup = Mock()
    save = AsyncMock()

    with (
        patch(
            "app.main.download_and_extract_repo",
            new=AsyncMock(return_value=str(repository_root)),
        ),
        patch(
            "app.main.parse_changed_files",
            new=AsyncMock(return_value=parsed_data),
        ),
        patch("app.main.save_parsed_ast_to_neo4j", new=save),
        patch("app.main.cleanup_downloaded_repo", new=cleanup),
    ):
        response = TestClient(app).post(
            "/api/ingest-repo",
            json={"url": "https://github.com/psf/requests"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "repo_name": "psf/requests",
    }
    save.assert_awaited_once_with(
        parsed_data,
        repo_name="psf/requests",
        replace_existing=True,
    )
    assert parsed_data[0]["file_path"] == "src/example.py"
    cleanup.assert_called_once_with(str(repository_root))


def test_ingest_repository_rejects_non_github_url() -> None:
    response = TestClient(app).post(
        "/api/ingest-repo",
        json={"url": "https://example.com/psf/requests"},
    )

    assert response.status_code == 422


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
