import asyncio
import logging
import os
import re
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable
from pydantic import BaseModel, Field, field_validator

from app.api import webhooks
from app.agent.graph import ask_code_agent
from app.db import close_neo4j_driver, fetch_graph_data
from app.db.graph_ops import save_parsed_ast_to_neo4j
from app.db.neo4j_client import close_driver
from app.services.github_service import (
    cleanup_downloaded_repo,
    download_and_extract_repo,
)
from app.services.parser_service import parse_changed_files


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

SUPPORTED_SOURCE_SUFFIXES = frozenset({".py", ".ts", ".tsx"})
IGNORED_REPOSITORY_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)
GITHUB_REPOSITORY_PART = re.compile(r"[A-Za-z0-9_.-]+")

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Release synchronous and asynchronous Neo4j drivers on shutdown."""

    yield
    close_driver()
    await close_neo4j_driver()


class ChatRequest(BaseModel):
    """Validated request body for the basic chat endpoint."""

    message: str = Field(min_length=1, max_length=10_000)
    repo_name: str = Field(min_length=3, max_length=201)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        """Trim the message and reject whitespace-only input."""

        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be blank")
        return stripped

    @field_validator("repo_name")
    @classmethod
    def repo_name_must_be_canonical(cls, value: str) -> str:
        """Require the same ``owner/repository`` key used by ingestion."""

        return _normalize_repo_identifier(value)


class IngestRepositoryRequest(BaseModel):
    """GitHub repository requested for on-demand graph ingestion."""

    url: str = Field(min_length=1, max_length=2_048)

    @field_validator("url")
    @classmethod
    def url_must_not_be_blank(cls, value: str) -> str:
        """Trim the URL and reject whitespace-only input."""

        stripped = value.strip()
        if not stripped:
            raise ValueError("url must not be blank")
        return stripped


def _normalize_repo_identifier(repo_name: str) -> str:
    """Validate and normalize an ``owner/repository`` identifier."""

    normalized = repo_name.strip().removesuffix(".git")
    parts = normalized.split("/")
    if (
        len(parts) != 2
        or not all(GITHUB_REPOSITORY_PART.fullmatch(part) for part in parts)
    ):
        raise ValueError("repo_name must use the 'owner/repository' format")
    return normalized


def _parse_github_repository_url(url: str) -> tuple[str, str]:
    """Extract an owner and repository from a canonical GitHub HTTPS URL."""

    parsed_url = urlparse(url)
    if parsed_url.scheme.lower() != "https" or parsed_url.hostname not in {
        "github.com",
        "www.github.com",
    }:
        raise ValueError("url must be an HTTPS github.com repository URL")

    decoded_path = unquote(parsed_url.path).strip("/")
    owner, repo = _normalize_repo_identifier(decoded_path).split("/", 1)
    return owner, repo


def _discover_repository_source_files(extracted_root: str) -> list[str]:
    """Walk an extracted repository and return supported source file paths."""

    source_files: list[str] = []
    for root, directory_names, file_names in os.walk(extracted_root):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in IGNORED_REPOSITORY_DIRECTORIES
        )
        for file_name in sorted(file_names):
            if Path(file_name).suffix.lower() in SUPPORTED_SOURCE_SUFFIXES:
                source_files.append(str(Path(root, file_name)))
    return source_files


def _use_repository_relative_paths(
    parsed_data: list[dict[str, Any]],
    extracted_root: str,
) -> None:
    """Replace random temporary paths with stable repository-relative paths."""

    repository_root = Path(extracted_root).resolve()
    for parsed_file in parsed_data:
        file_path = parsed_file.get("file_path")
        if isinstance(file_path, str):
            parsed_file["file_path"] = (
                Path(file_path).resolve().relative_to(repository_root).as_posix()
            )


app = FastAPI(
    title="Code Knowledge Graph Agent API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(webhooks.router)


@app.get("/api/graph", tags=["graph"])
async def get_graph(
    repo_name: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return one repository graph, or an empty graph without a scope."""

    if repo_name is None:
        return {"nodes": [], "edges": []}

    try:
        normalized_repo_name = _normalize_repo_identifier(repo_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    try:
        return await fetch_graph_data(normalized_repo_name)
    except AuthError as exc:
        logger.warning("Neo4j rejected the configured credentials")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j authentication failed; check backend/.env credentials",
        ) from exc
    except ServiceUnavailable as exc:
        logger.warning("Neo4j is unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j is unavailable",
        ) from exc
    except Neo4jError as exc:
        logger.exception("Neo4j graph query failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Neo4j graph query failed",
        ) from exc


@app.post("/api/chat", tags=["chat"])
async def chat(request: ChatRequest) -> dict[str, str]:
    """Answer a code-graph question with the LangGraph Claude agent."""

    try:
        ai_response = await ask_code_agent(request.message, request.repo_name)
    except Exception as exc:
        logger.exception("Code agent request failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The code agent could not complete the request",
        ) from exc
    return {"response": ai_response}


@app.post("/api/ingest-repo", tags=["ingestion"])
async def ingest_repository(
    request: IngestRepositoryRequest,
) -> dict[str, str]:
    """Download, parse, and persist a public GitHub repository on demand."""

    try:
        owner, repository = _parse_github_repository_url(request.url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    canonical_repo_name = f"{owner}/{repository}"
    extracted_root: str | None = None
    try:
        extracted_root = await download_and_extract_repo(owner, repository)
        source_files = await asyncio.to_thread(
            _discover_repository_source_files,
            extracted_root,
        )
        parsed_data = await parse_changed_files(source_files)
        _use_repository_relative_paths(parsed_data, extracted_root)
        await save_parsed_ast_to_neo4j(
            parsed_data,
            repo_name=canonical_repo_name,
            replace_existing=True,
        )
    except httpx.HTTPStatusError as exc:
        response_status = exc.response.status_code
        if response_status == status.HTTP_404_NOT_FOUND:
            detail = "GitHub repository or branch was not found"
            api_status = status.HTTP_404_NOT_FOUND
        else:
            detail = f"GitHub archive download failed with status {response_status}"
            api_status = status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=api_status, detail=detail) from exc
    except (httpx.RequestError, zipfile.BadZipFile, ValueError) as exc:
        logger.warning("Unable to download or extract %s: %s", canonical_repo_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub repository download or extraction failed",
        ) from exc
    except AuthError as exc:
        logger.warning("Neo4j rejected ingestion credentials")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j authentication failed during repository ingestion",
        ) from exc
    except ServiceUnavailable as exc:
        logger.warning("Neo4j is unavailable during repository ingestion")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j is unavailable during repository ingestion",
        ) from exc
    except Neo4jError as exc:
        logger.exception("Neo4j repository ingestion failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Neo4j repository ingestion failed",
        ) from exc
    finally:
        if extracted_root is not None:
            cleanup_downloaded_repo(extracted_root)

    return {
        "status": "success",
        "repo_name": canonical_repo_name,
    }


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, Literal["ok"]]:
    """Report process health without calling external dependencies."""

    return {"status": "ok"}
