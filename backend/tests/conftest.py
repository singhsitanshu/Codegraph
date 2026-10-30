"""Shared fixtures for tests that need the configured live Neo4j."""

from collections.abc import Iterator

import pytest
from neo4j import Driver, GraphDatabase

from app.config import settings


@pytest.fixture
def live_neo4j() -> Iterator[Driver]:
    """Yield a sync driver to the configured Neo4j, or skip when unreachable.

    The application itself only runs an async driver; tests use this separate
    driver to arrange and inspect graph state around the code under test.
    """

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        connection_timeout=5.0,
        connection_acquisition_timeout=5.0,
    )
    try:
        try:
            driver.verify_connectivity()
        except Exception:
            pytest.skip(
                "Neo4j is unavailable; integration tests require a live database"
            )
        yield driver
    finally:
        driver.close()
