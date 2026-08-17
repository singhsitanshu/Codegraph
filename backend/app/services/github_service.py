"""GitHub REST/raw-content access used by the webhook pipeline."""

from urllib.parse import quote

import httpx


RAW_GITHUB_BASE_URL = "https://raw.githubusercontent.com"


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
        headers={
            "Accept": "text/plain",
            "User-Agent": "code-knowledge-graph-agent",
        },
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
