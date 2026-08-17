import hashlib
import hmac
import logging
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic_settings import BaseSettings, SettingsConfigDict


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    github_webhook_secret: str
    github_token: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
app = FastAPI(title="GitHub Webhook Listener")


def verify_signature(body: bytes, signature: str | None) -> None:
    """Verify GitHub's SHA-256 webhook signature without timing leaks."""
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid signature",
        )

    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )


def push_files(payload: dict[str, Any]) -> list[str]:
    files: set[str] = set()
    for commit in payload.get("commits", []):
        for key in ("added", "modified", "removed"):
            files.update(commit.get(key, []))
    return sorted(files)


async def pull_request_files(payload: dict[str, Any]) -> list[str]:
    pull_request_url = payload.get("pull_request", {}).get("url")
    if not pull_request_url:
        return []

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    files: list[str] = []
    page = 1
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            response = await client.get(
                f"{pull_request_url}/files",
                headers=headers,
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            files.extend(item["filename"] for item in batch)
            if len(batch) < 100:
                break
            page += 1
    return sorted(set(files))


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await request.body()
    verify_signature(body, x_hub_signature_256)

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if x_github_event == "push":
        files = push_files(payload)
    elif x_github_event == "pull_request":
        try:
            files = await pull_request_files(payload)
        except httpx.HTTPError as exc:
            logger.exception("Unable to retrieve pull request files")
            raise HTTPException(
                status_code=502, detail="Unable to retrieve pull request files"
            ) from exc
    else:
        return {"status": "ignored", "event": x_github_event}

    logger.info("Modified files (%s): %s", x_github_event, files)
    return {"status": "accepted", "event": x_github_event, "file_count": len(files)}
