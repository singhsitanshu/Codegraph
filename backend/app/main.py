import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import aclosing, asynccontextmanager, contextmanager
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.agent.graph import ask_code_agent_with_metrics
from app.config import settings
from app.database.driver import close_neo4j_driver
from app.database.errors import NEO4J_ERRORS, Neo4jFailureDetails, is_neo4j_unavailable
from app.graph.queries import fetch_node_code
from app.graph.schema import initialize_database
from app.graph.view import fetch_graph_view
from app.graph.writer import delete_all_repository_graphs, delete_repository_graph
from app.ingestion import ingestion_progress
from app.ingestion.repository_ingestion import (
    IngestionComplete,
    IngestionFailed,
    RepositoryIngestionEvent,
    ingest_github_repository,
)
from app.repositories.names import (
    GitHubRepository,
    GitHubRepositoryUrl,
    RepositoryName,
)
from app.webhooks import routes as webhook_routes


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

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


@contextmanager
def _neo4j_errors_as_http(details: Neo4jFailureDetails) -> Iterator[None]:
    """Translate Neo4j failures raised in the block into API errors."""

    try:
        yield
    except NEO4J_ERRORS as exc:
        status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if is_neo4j_unavailable(exc)
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        raise HTTPException(
            status_code=status_code,
            detail=details.describe(exc),
        ) from exc


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
app.include_router(webhook_routes.router)


@app.get("/api/graph", tags=["graph"])
async def get_graph(
    repo_name: RepositoryName | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return one repository graph, or an empty graph without a scope."""

    if repo_name is None:
        return {"nodes": [], "edges": []}

    with _neo4j_errors_as_http(GRAPH_QUERY_FAILURES):
        return await fetch_graph_view(repo_name)


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


def _ingestion_record(event: RepositoryIngestionEvent) -> str:
    """Serialize one repository ingestion event as an NDJSON record."""

    if isinstance(event, IngestionComplete):
        return _ndjson_record(
            status="Repository ingestion complete.",
            progress=ingestion_progress.COMPLETE,
            repo_name=event.repo_name,
            total_repo_tokens=event.total_repo_tokens,
        )
    if isinstance(event, IngestionFailed):
        return _ndjson_record(
            status="Repository ingestion failed.",
            progress=event.progress,
            error=event.error,
        )
    return _ndjson_record(status=event.status, progress=event.progress)


async def _stream_repository_ingestion(
    repository: GitHubRepository,
) -> AsyncIterator[str]:
    """Stream repository ingestion as NDJSON progress records."""

    async with aclosing(ingest_github_repository(repository)) as events:
        async for event in events:
            yield _ingestion_record(event)


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
