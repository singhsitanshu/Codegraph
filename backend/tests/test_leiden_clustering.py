"""Live Leiden clustering checks; require the configured Neo4j with GDS."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from app.db import close_neo4j_driver, neo4j_client
from app.db.graph_ops import save_parsed_ast_to_neo4j
from app.services.parser_service import CodeParser

TEST_REPO_NAME = "test/leiden-two-groups"
CLEANUP_QUERY = "MATCH (n {repo_name: $repo_name}) DETACH DELETE n"


def _group_source(prefix: str) -> str:
    """Four functions that all call one another and nothing outside."""

    names = [f"{prefix}_{index}" for index in range(4)]
    return "\n\n".join(
        f"def {name}():\n"
        + "".join(f"    {other}()\n" for other in names if other != name)
        for name in names
    )


def _parse(file_path: str, source: str) -> dict[str, object]:
    return asyncio.run(
        CodeParser().parse_file(
            file_path,
            source.encode("utf-8"),
            repository=TEST_REPO_NAME,
        )
    )


async def _fake_embeddings(texts: list[str]) -> list[list[float]]:
    return [[0.1, 0.2, 0.3] for _ in texts]


@pytest.fixture
def gds_database() -> Iterator[None]:
    if neo4j_client.driver is None:
        neo4j_client.driver = neo4j_client._initialize_driver()
    if neo4j_client.driver is None:
        pytest.skip("Neo4j is unavailable; integration tests require a live database")
    with neo4j_client.driver.session() as session:
        try:
            session.run("RETURN gds.version() AS version").consume()
        except Exception:
            neo4j_client.close_driver()
            pytest.skip("Neo4j Graph Data Science is not installed")
        session.run(CLEANUP_QUERY, repo_name=TEST_REPO_NAME).consume()
    try:
        yield
    finally:
        if neo4j_client.driver is not None:
            with neo4j_client.driver.session() as session:
                session.run(CLEANUP_QUERY, repo_name=TEST_REPO_NAME).consume()
        neo4j_client.close_driver()


def test_two_connected_groups_produce_exactly_two_communities(
    gds_database: None,
) -> None:
    parsed_data = [
        _parse("src/alpha.py", _group_source("alpha")),
        _parse("src/beta.py", _group_source("beta")),
    ]

    async def save() -> None:
        try:
            await save_parsed_ast_to_neo4j(
                parsed_data,
                TEST_REPO_NAME,
                replace_existing=True,
            )
        finally:
            await close_neo4j_driver()

    with patch(
        "app.db.graph_ops.generate_embeddings",
        side_effect=_fake_embeddings,
    ), patch(
        "app.db.graph_ops.label_and_store_communities",
        new=AsyncMock(),
    ):
        asyncio.run(save())

    assert neo4j_client.driver is not None
    with neo4j_client.driver.session() as session:
        rows = session.run(
            "MATCH (function:Function {repo_name: $repo_name}) "
            "RETURN function.file_path AS file_path, "
            "collect(DISTINCT function.leiden_community) AS communities",
            repo_name=TEST_REPO_NAME,
        ).data()
        unclustered = session.run(
            "MATCH (node {repo_name: $repo_name}) "
            "WHERE NOT node:Function AND node.leiden_community IS NOT NULL "
            "RETURN count(node) AS count",
            repo_name=TEST_REPO_NAME,
        ).single(strict=True)["count"]

    communities_by_file = {row["file_path"]: row["communities"] for row in rows}
    assert set(communities_by_file) == {"src/alpha.py", "src/beta.py"}
    assert all(len(ids) == 1 for ids in communities_by_file.values())
    assert communities_by_file["src/alpha.py"] != communities_by_file["src/beta.py"]
    assert unclustered == 0
