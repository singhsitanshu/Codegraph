import asyncio
import json
import logging
import os
import zipfile
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable
from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.api import webhooks
from app.agent.graph import ask_code_agent_with_metrics
from app.config import settings
from app.db import close_neo4j_driver, fetch_graph_data, fetch_node_code
from app.db.graph_ops import (
    delete_all_repository_graphs,
    delete_repository_graph,
    save_parsed_ast_to_neo4j_with_progress,
)
from app.db.neo4j_client import initialize_database
from app.services.github_service import download_and_extract_repo
from app.services.parser_service import (
    SUPPORTED_EXTENSIONS,
    IdentifiedFile,
    ParsedSource,
    identify_parsed_source,
    parse_changed_files_with_progress,
)
from app.utils import ingestion_progress
from app.utils.repository import (
    GitHubRepository,
    GitHubRepositoryUrl,
    RepositoryName,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

SUPPORTED_SOURCE_SUFFIXES = frozenset(SUPPORTED_EXTENSIONS)
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


@dataclass(frozen=True)
class Neo4jFailureDetails:
    """Client-facing messages for one operation's Neo4j failure modes."""

    authentication: str
    unavailable: str
    failure: str


GRAPH_QUERY_FAILURES = Neo4jFailureDetails(
    authentication="Neo4j authentication failed; check backend/.env credentials",
    unavailable="Neo4j is unavailable",
    failure="Neo4j graph query failed",
)
NODE_SOURCE_FAILURES = Neo4jFailureDetails(
    authentication="Neo4j authentication failed; check backend/.env credentials",
    unavailable="Neo4j is unavailable",
    failure="Neo4j node source query failed",
)
REPOSITORY_DELETION_FAILURES = Neo4jFailureDetails(
    authentication="Neo4j authentication failed during repository deletion",
    unavailable="Neo4j is unavailable during repository deletion",
    failure="Neo4j repository deletion failed",
)
REPOSITORY_INGESTION_FAILURES = Neo4jFailureDetails(
    authentication="Neo4j authentication failed during repository ingestion",
    unavailable="Neo4j is unavailable during repository ingestion",
    failure="Neo4j repository ingestion failed",
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize Neo4j, clear stale session graphs, and release the driver."""

    try:
        await initialize_database()
        await delete_all_repository_graphs()
        yield
    finally:
        await close_neo4j_driver()


class ChatRequest(BaseModel):
    """Validated request body for the basic chat endpoint."""

    message: str = Field(min_length=1, max_length=10_000)
    repo_name: RepositoryName

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        """Trim the message and reject whitespace-only input."""

        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be blank")
        return stripped


class IngestRepositoryRequest(BaseModel):
    """GitHub repository requested for on-demand graph ingestion."""

    repository: GitHubRepositoryUrl = Field(alias="url")


class RepositoryCleanupRequest(BaseModel):
    """Repository graph to remove during browser lifecycle cleanup."""

    repo_name: RepositoryName


NodeId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Neo4j element ID of a graph node, trimmed and required to be non-blank."""


def _neo4j_failure(
    exc: Neo4jError | ServiceUnavailable,
    details: Neo4jFailureDetails,
) -> tuple[int, str]:
    """Log a Neo4j failure and return its HTTP status and client detail."""

    if isinstance(exc, AuthError):
        logger.warning(details.authentication)
        return status.HTTP_503_SERVICE_UNAVAILABLE, details.authentication
    if isinstance(exc, ServiceUnavailable):
        logger.warning(details.unavailable)
        return status.HTTP_503_SERVICE_UNAVAILABLE, details.unavailable
    logger.exception(details.failure)
    return status.HTTP_500_INTERNAL_SERVER_ERROR, details.failure


@contextmanager
def _neo4j_errors_as_http(details: Neo4jFailureDetails) -> Iterator[None]:
    """Translate Neo4j failures raised in the block into API errors."""

    try:
        yield
    except (Neo4jError, ServiceUnavailable) as exc:
        status_code, detail = _neo4j_failure(exc, details)
        raise HTTPException(status_code=status_code, detail=detail) from exc


def _discover_repository_source_files(extracted_root: Path) -> list[str]:
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


def _identify_repository_files(
    parsed_sources: list[ParsedSource],
    extracted_root: Path,
    repository: str,
) -> list[IdentifiedFile]:
    """Identify files parsed from a temporary checkout by repository-relative paths."""

    repository_root = extracted_root.resolve()
    return [
        identify_parsed_source(
            parsed_source,
            repository=repository,
            file_path=(
                Path(parsed_source.file_path)
                .resolve()
                .relative_to(repository_root)
                .as_posix()
            ),
        )
        for parsed_source in parsed_sources
    ]


app = FastAPI(
    title="Code Knowledge Graph Agent API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(webhooks.router)


@app.get("/api/graph", tags=["graph"])
async def get_graph(
    repo_name: RepositoryName | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return one repository graph, or an empty graph without a scope."""

    if repo_name is None:
        return {"nodes": [], "edges": []}

    with _neo4j_errors_as_http(GRAPH_QUERY_FAILURES):
        return await fetch_graph_data(repo_name)


@app.get("/api/node/{node_id}/code", tags=["graph"])
async def get_node_code(
    node_id: NodeId,
    repo_name: RepositoryName,
) -> dict[str, str]:
    """Return one repository-scoped function's source code on demand."""

    with _neo4j_errors_as_http(NODE_SOURCE_FAILURES):
        source = await fetch_node_code(node_id, repo_name)

    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source code was not found for this function",
        )
    return source


async def _delete_repository_scope(repo_name: str) -> dict[str, str]:
    """Delete one validated scope and map Neo4j failures to API errors."""

    with _neo4j_errors_as_http(REPOSITORY_DELETION_FAILURES):
        await delete_repository_graph(repo_name)
    return {"status": "success", "repo_name": repo_name}


@app.delete("/api/repo", tags=["graph"])
async def cleanup_repository(request: RepositoryCleanupRequest) -> dict[str, str]:
    """Delete the active graph from a browser unload keepalive request."""

    return await _delete_repository_scope(request.repo_name)


@app.delete("/api/repositories/{repo_name:path}", tags=["graph"])
async def delete_repository(repo_name: RepositoryName) -> dict[str, str]:
    """Permanently delete one repository-scoped graph from Neo4j."""

    return await _delete_repository_scope(repo_name)


@app.post("/api/chat", tags=["chat"])
async def chat(request: ChatRequest) -> dict[str, Any]:
    """Answer a code-graph question with the LangGraph Claude agent."""

    try:
        agent_result = await ask_code_agent_with_metrics(
            request.message,
            request.repo_name,
        )
    except Exception as exc:
        logger.exception("Code agent request failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The code agent could not complete the request",
        ) from exc
    return {
        "response": agent_result.answer,
        "metrics": agent_result.metrics.as_dict(),
    }


def _ndjson_record(**payload: object) -> str:
    """Serialize one newline-delimited JSON progress record."""

    return json.dumps(payload, separators=(",", ":")) + "\n"


def _ingestion_failure_record(progress: int, error: str) -> str:
    """Serialize the terminal NDJSON record for a failed ingestion."""

    return _ndjson_record(
        status="Repository ingestion failed.",
        progress=progress,
        error=error,
    )


async def _stream_repository_ingestion(
    repository: GitHubRepository,
) -> AsyncIterator[str]:
    """Run repository ingestion while emitting NDJSON progress records."""

    canonical_repo_name = repository.full_name
    current_progress = 0
    try:
        current_progress = ingestion_progress.DOWNLOAD_STARTED
        yield _ndjson_record(
            status="Downloading repository...",
            progress=current_progress,
        )
        async with download_and_extract_repo(
            repository.owner,
            repository.name,
        ) as extracted_root:
            current_progress = ingestion_progress.DOWNLOADED
            yield _ndjson_record(
                status="Repository downloaded and extracted.",
                progress=current_progress,
            )
            source_files = await asyncio.to_thread(
                _discover_repository_source_files,
                extracted_root,
            )

            total_repo_tokens = 0
            parsed_by_index: dict[int, ParsedSource] = {}
            if source_files:
                async for file_progress in parse_changed_files_with_progress(
                    source_files
                ):
                    total_repo_tokens += file_progress.source_tokens
                    if file_progress.result is not None:
                        parsed_by_index[file_progress.index] = file_progress.result
                    current_progress = ingestion_progress.PARSING.at(
                        file_progress.processed,
                        file_progress.total,
                    )
                    yield _ndjson_record(
                        status=(
                            f"Parsing files ({file_progress.processed}/"
                            f"{file_progress.total})..."
                        ),
                        progress=current_progress,
                    )
            else:
                current_progress = ingestion_progress.PARSING.end
                yield _ndjson_record(
                    status="No supported source files found.",
                    progress=current_progress,
                )

            if len(parsed_by_index) != len(source_files):
                logger.warning(
                    "Aborting full ingest for %s because a supported source file "
                    "could not be parsed",
                    canonical_repo_name,
                )
                yield _ingestion_failure_record(
                    current_progress,
                    "A supported source file could not be parsed",
                )
                return

            identified_files = _identify_repository_files(
                [parsed_by_index[index] for index in range(len(source_files))],
                extracted_root,
                repository=canonical_repo_name,
            )
            logger.info(
                "Full repository token baseline for %s: %d",
                canonical_repo_name,
                total_repo_tokens,
            )

            current_progress = ingestion_progress.DATABASE_STARTED
            yield _ndjson_record(
                status="Batching data to Neo4j...",
                progress=current_progress,
            )
            async for database_progress in save_parsed_ast_to_neo4j_with_progress(
                identified_files,
                repo_name=canonical_repo_name,
                replace_existing=True,
                total_repo_tokens=total_repo_tokens,
            ):
                current_progress = database_progress.progress
                yield _ndjson_record(
                    status=database_progress.status,
                    progress=current_progress,
                )

            yield _ndjson_record(
                status="Repository ingestion complete.",
                progress=ingestion_progress.COMPLETE,
                repo_name=canonical_repo_name,
                total_repo_tokens=total_repo_tokens,
            )
    except httpx.HTTPStatusError as exc:
        response_status = exc.response.status_code
        if response_status == status.HTTP_404_NOT_FOUND:
            detail = "GitHub repository was not found"
        else:
            detail = f"GitHub archive download failed with status {response_status}"
        logger.warning("Unable to ingest %s: %s", canonical_repo_name, detail)
        yield _ingestion_failure_record(current_progress, detail)
    except (httpx.RequestError, zipfile.BadZipFile, ValueError) as exc:
        logger.warning("Unable to download or extract %s: %s", canonical_repo_name, exc)
        yield _ingestion_failure_record(
            current_progress,
            "GitHub repository download or extraction failed",
        )
    except (Neo4jError, ServiceUnavailable) as exc:
        _, detail = _neo4j_failure(exc, REPOSITORY_INGESTION_FAILURES)
        yield _ingestion_failure_record(current_progress, detail)
    except Exception:
        logger.exception("Unexpected repository ingestion failure")
        yield _ingestion_failure_record(
            current_progress,
            "Unexpected repository ingestion failure",
        )


@app.post("/api/ingest-repo", tags=["ingestion"])
async def ingest_repository(
    request: IngestRepositoryRequest,
) -> StreamingResponse:
    """Stream progress while ingesting a public GitHub repository."""

    return StreamingResponse(
        _stream_repository_ingestion(request.repository),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, Literal["ok"]]:
    """Report process health without calling external dependencies."""

    return {"status": "ok"}
