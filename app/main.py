import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    github_webhook_secret: str
    github_token: str | None = None

    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str = "neo4j"

    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-5"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
app = FastAPI(title="GitHub Webhook Listener")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


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


@app.get("/api/graph")
def get_graph() -> dict[str, list[dict[str, Any]]]:
    from database import Neo4jDatabase
    from neo4j.exceptions import AuthError, ServiceUnavailable

    try:
        with Neo4jDatabase() as database:
            return database.get_call_graph()
    except AuthError as exc:
        logger.warning("Neo4j rejected the configured credentials")
        raise HTTPException(
            status_code=503,
            detail=(
                "Neo4j authentication failed. Update NEO4J_USER and "
                "NEO4J_PASSWORD in .env, then restart FastAPI."
            ),
        ) from exc
    except ServiceUnavailable as exc:
        logger.warning("Neo4j is unavailable at %s", settings.neo4j_uri)
        raise HTTPException(
            status_code=503,
            detail=f"Neo4j is unavailable at {settings.neo4j_uri}.",
        ) from exc
    except Exception as exc:
        logger.exception("Unable to retrieve the Neo4j call graph")
        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve graph data from Neo4j",
        ) from exc


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    from agent import stream_agent
    from anthropic import AuthenticationError, NotFoundError

    def event_stream():
        try:
            for token in stream_agent(request.message.strip()):
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield "event: done\ndata: [DONE]\n\n"
        except NotFoundError as exc:
            logger.warning("Anthropic model is unavailable: %s", exc)
            payload = json.dumps(
                {
                    "error": (
                        f"Anthropic model '{settings.anthropic_model}' is unavailable. "
                        "Set ANTHROPIC_MODEL to an active Claude API model."
                    )
                }
            )
            yield f"event: error\ndata: {payload}\n\n"
        except AuthenticationError:
            logger.warning("Anthropic rejected the configured API key")
            payload = json.dumps(
                {"error": "Anthropic authentication failed. Check ANTHROPIC_API_KEY."}
            )
            yield f"event: error\ndata: {payload}\n\n"
        except Exception as exc:
            logger.exception("Unable to stream the agent response")
            payload = json.dumps({"error": str(exc)})
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
