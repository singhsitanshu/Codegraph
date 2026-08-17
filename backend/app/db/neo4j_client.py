"""Synchronous Neo4j client and FastAPI session dependency."""

import logging
import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase, Session


logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env", override=False)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def _initialize_driver() -> Driver | None:
    """Create a driver and verify that the configured database is reachable."""

    candidate: Driver | None = None
    try:
        candidate = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            connection_timeout=5.0,
            connection_acquisition_timeout=5.0,
        )
        candidate.verify_connectivity()
    except Exception as exc:
        logger.error("Failed to connect to Neo4j at %s: %s", NEO4J_URI, exc)
        if candidate is not None:
            candidate.close()
        return None

    logger.info("Successfully connected to Neo4j at %s", NEO4J_URI)
    return candidate


driver: Driver | None = _initialize_driver()


def get_db_session() -> Generator[Session, None, None]:
    """Yield a Neo4j session for FastAPI and close it after the request.

    A failed import-time connection is retried when the dependency is first
    requested, allowing the API and Neo4j containers to start concurrently.

    Raises:
        RuntimeError: If Neo4j remains unreachable or rejects authentication.
    """

    global driver
    if driver is None:
        driver = _initialize_driver()
    if driver is None:
        raise RuntimeError("Neo4j driver is not initialized")

    session = driver.session()
    try:
        yield session
    finally:
        session.close()


def close_driver() -> None:
    """Close the global synchronous driver during application shutdown."""

    global driver
    if driver is not None:
        driver.close()
        driver = None
