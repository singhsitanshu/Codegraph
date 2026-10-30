"""The process-wide async Neo4j driver shared by every database module."""

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import settings


_driver: AsyncDriver | None = None


def get_neo4j_driver() -> AsyncDriver:
    """Return the process-wide Neo4j driver, creating it on first use."""

    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


async def close_neo4j_driver() -> None:
    """Close the process-wide Neo4j driver during application shutdown."""

    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
