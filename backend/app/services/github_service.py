"""GitHub download and raw-content access used by ingestion pipelines."""

import asyncio
import io
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import settings


RAW_GITHUB_BASE_URL = "https://raw.githubusercontent.com"
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "code-knowledge-graph-agent",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ``download_and_extract_repo`` returns a string as required by the service
# boundary, so retain ownership of each TemporaryDirectory until the API's
# finally block explicitly releases it with ``cleanup_downloaded_repo``.
_temporary_repositories: dict[str, tempfile.TemporaryDirectory[str]] = {}


def _github_headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    """Build GitHub headers, including optional configured authentication."""

    headers = {**GITHUB_HEADERS, "Accept": accept}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    return headers


async def _get_default_branch(
    client: httpx.AsyncClient,
    encoded_owner: str,
    encoded_repo: str,
) -> str:
    """Read and validate a repository's configured default branch."""

    metadata_url = f"{GITHUB_API_BASE_URL}/repos/{encoded_owner}/{encoded_repo}"
    response = await client.get(metadata_url)
    response.raise_for_status()
    payload = response.json()
    default_branch = (
        payload.get("default_branch") if isinstance(payload, dict) else None
    )
    if not isinstance(default_branch, str) or not default_branch.strip():
        raise ValueError("GitHub repository metadata has no default_branch")
    return default_branch.strip()


def _extract_zip_safely(archive_bytes: bytes, destination: Path) -> Path:
    """Extract a GitHub zipball without allowing paths outside destination."""

    destination = destination.resolve()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        members = archive.infolist()
        if not members:
            raise ValueError("GitHub returned an empty repository archive")

        for member in members:
            member_path = (destination / member.filename).resolve()
            if not member_path.is_relative_to(destination):
                raise ValueError("Repository archive contains an unsafe path")
        archive.extractall(destination)

    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise ValueError("GitHub repository archive has an unexpected layout")
    return roots[0]


async def download_and_extract_repo(
    repo_owner: str,
    repo_name: str,
    branch: str | None = None,
) -> str:
    """Download and extract a GitHub repository branch into temporary storage.

    The returned extracted-root path remains valid until
    :func:`cleanup_downloaded_repo` is called. Callers should always release it
    in a ``finally`` block. When ``branch`` is omitted, GitHub repository
    metadata supplies the actual default branch.
    """

    normalized_owner = repo_owner.strip()
    normalized_repo = repo_name.strip()
    normalized_branch = branch.strip() if branch is not None else None
    if not normalized_owner or not normalized_repo:
        raise ValueError("repo_owner and repo_name must not be blank")
    if branch is not None and not normalized_branch:
        raise ValueError("branch must not be blank when provided")

    encoded_owner = quote(normalized_owner, safe="")
    encoded_repo = quote(normalized_repo, safe="")
    temporary_directory = tempfile.TemporaryDirectory(prefix="github-repo-")

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(60.0),
            headers=_github_headers(),
        ) as client:
            selected_branch = normalized_branch or await _get_default_branch(
                client,
                encoded_owner,
                encoded_repo,
            )
            encoded_branch = quote(selected_branch, safe="")
            archive_url = (
                f"{GITHUB_API_BASE_URL}/repos/{encoded_owner}/{encoded_repo}/"
                f"zipball/{encoded_branch}"
            )
            response = await client.get(archive_url)
            response.raise_for_status()

        extracted_root = await asyncio.to_thread(
            _extract_zip_safely,
            response.content,
            Path(temporary_directory.name),
        )
        extracted_root_path = str(extracted_root)
        _temporary_repositories[extracted_root_path] = temporary_directory
        return extracted_root_path
    except Exception:
        temporary_directory.cleanup()
        raise


def cleanup_downloaded_repo(extracted_root: str) -> None:
    """Delete temporary storage previously returned by the download service."""

    temporary_directory = _temporary_repositories.pop(extracted_root, None)
    if temporary_directory is not None:
        temporary_directory.cleanup()


async def fetch_raw_file_content(
    owner: str,
    repo: str,
    file_path: str,
    commit_sha: str,
) -> str:
    """Fetch one repository file exactly as it existed at a commit.

    Args:
        owner: GitHub repository owner or organization.
        repo: GitHub repository name.
        file_path: Repository-relative file path.
        commit_sha: Immutable Git commit SHA supplied by the webhook.

    Returns:
        The decoded text response returned by GitHub.

    Raises:
        httpx.HTTPStatusError: If GitHub returns a non-success status.
        httpx.RequestError: If the request cannot be completed.
    """

    encoded_owner = quote(owner, safe="")
    encoded_repo = quote(repo, safe="")
    encoded_sha = quote(commit_sha, safe="")
    encoded_path = quote(file_path.lstrip("/"), safe="/")
    url = (
        f"{RAW_GITHUB_BASE_URL}/{encoded_owner}/{encoded_repo}/"
        f"{encoded_sha}/{encoded_path}"
    )

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(20.0),
        headers=_github_headers(accept="text/plain"),
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
