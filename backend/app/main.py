import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable
from pydantic import BaseModel, Field, field_validator

from app.api import webhooks
from app.agent.graph import ask_code_agent
from app.db import close_neo4j_driver, fetch_graph_data
from app.db.neo4j_client import close_driver


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Release synchronous and asynchronous Neo4j drivers on shutdown."""

    yield
    close_driver()
    await close_neo4j_driver()


class ChatRequest(BaseModel):
    """Validated request body for the basic chat endpoint."""

    message: str = Field(min_length=1, max_length=10_000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        """Trim the message and reject whitespace-only input."""

        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be blank")
        return stripped


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
async def get_graph() -> dict[str, list[dict[str, Any]]]:
    """Return Neo4j nodes and edges in web graph component formats."""

    try:
        return await fetch_graph_data()
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
        ai_response = await ask_code_agent(request.message)
    except Exception as exc:
        logger.exception("Code agent request failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The code agent could not complete the request",
        ) from exc
    return {"response": ai_response}


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, Literal["ok"]]:
    """Report process health without calling external dependencies."""

    return {"status": "ok"}
