"""Disposable Neo4j verification; requires a working Docker daemon and image."""

import asyncio
import shutil
import subprocess
import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from neo4j import AsyncGraphDatabase, GraphDatabase

from app.db import fetch_graph_data, fetch_node_code
from app.db.graph_ops import save_parsed_ast_to_neo4j
from app.services.parser_service import CodeParser

REPO = "integration/identity"
PASSWORD = "integration-password"
IMAGE = "neo4j:5.26"


@pytest.fixture(scope="module")
def disposable_neo4j():
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable; disposable Neo4j not started")
    daemon = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True)
    if daemon.returncode:
        pytest.skip("Docker daemon is unavailable; disposable Neo4j not started")
    name = f"codegraph-identity-test-{uuid4().hex[:12]}"
    started = subprocess.run(
        ["docker", "run", "--rm", "-d", "--name", name,
         "-e", f"NEO4J_AUTH=neo4j/{PASSWORD}", "-p", "127.0.0.1::7687", IMAGE],
        capture_output=True, text=True, timeout=180,
    )
    if started.returncode:
        pytest.fail(f"Unable to start disposable Neo4j: {started.stderr.strip()}")
    try:
        port_result = subprocess.run(["docker", "port", name, "7687/tcp"], capture_output=True, text=True, check=True)
        port = port_result.stdout.strip().rsplit(":", 1)[-1]
        uri = f"bolt://127.0.0.1:{port}"
        driver = GraphDatabase.driver(uri, auth=("neo4j", PASSWORD), connection_timeout=2)
        for _ in range(60):
            try:
                driver.verify_connectivity()
                break
            except Exception:
                time.sleep(1)
        else:
            pytest.fail("Disposable Neo4j did not become ready within 60 seconds")
        try:
            with driver.session() as session:
                session.run("CREATE CONSTRAINT function_repo_entity_id IF NOT EXISTS FOR (fn:Function) REQUIRE (fn.repo_name, fn.entity_id) IS UNIQUE").consume()
                session.run("CREATE CONSTRAINT unresolved_call_repo_id IF NOT EXISTS FOR (call:UnresolvedCall) REQUIRE (call.repo_name, call.call_id) IS UNIQUE").consume()
            yield uri, driver
        finally:
            driver.close()
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)


async def _fake_embeddings(texts):
    return [[0.1, 0.2, 0.3] for _ in texts]


def test_persisted_identity_calls_source_and_refresh(disposable_neo4j):
    uri, sync_driver = disposable_neo4j

    async def run():
        async_driver = AsyncGraphDatabase.driver(uri, auth=("neo4j", PASSWORD))
        parser = CodeParser()
        async def parse(path, code):
            return await parser.parse_file(path, code, repository=REPO)
        auth = await parse("src/auth.py", b"def validate():\n return 'auth'\ndef caller():\n validate()\n remote()\n")
        payments = await parse("src/payments.py", b"def validate():\n return 'payments'\n")
        try:
            with (
                patch("app.db.graph_ops.get_neo4j_driver", return_value=async_driver),
                patch("app.db.get_neo4j_driver", return_value=async_driver),
                patch("app.db.graph_ops.generate_embeddings", side_effect=_fake_embeddings),
                patch("app.db.graph_ops.run_leiden_clustering", new=AsyncMock()),
                patch("app.db.graph_ops.label_and_store_communities", new=AsyncMock()),
            ):
                await save_parsed_ast_to_neo4j([auth, payments], REPO, replace_existing=True)
                graph = await fetch_graph_data(REPO)
                validates = [n for n in graph["nodes"] if n["data"].get("name") == "validate"]
                assert len(validates) == 2
                assert len({n["data"]["entity_id"] for n in validates}) == 2
                codes = [await fetch_node_code(n["id"], REPO) for n in validates]
                assert {c["file_path"] for c in codes} == {"src/auth.py", "src/payments.py"}
                assert {c["code"].strip().splitlines()[-1] for c in codes} == {"return 'auth'", "return 'payments'"}
                assert len([e for e in graph["edges"] if e["label"] == "CALLS"]) == 1
                assert len([e for e in graph["edges"] if e["label"] == "HAS_UNRESOLVED_CALL"]) == 1

                await save_parsed_ast_to_neo4j([auth, payments], REPO, replace_existing=True)
                with sync_driver.session() as session:
                    record = session.run("MATCH (f:Function {repo_name: $repo}) RETURN count(f) AS n, count(DISTINCT f.entity_id) AS distinct_ids", repo=REPO).single()
                    assert (record["n"], record["distinct_ids"]) == (3, 3)
                    defines = session.run("MATCH (file:File {repo_name: $repo})-[:DEFINES]->(f:Function) RETURN file.path AS path, f.file_path AS stored", repo=REPO).data()
                    assert len(defines) == 3 and all(row["path"] == row["stored"] for row in defines)
                    assert session.run("MATCH (:Function {repo_name: $repo})-[r:CALLS]->(:Function) RETURN count(r) AS n", repo=REPO).single()["n"] == 1
                    assert session.run("MATCH (u:UnresolvedCall {repo_name: $repo}) RETURN count(u) AS n", repo=REPO).single()["n"] == 1

                changed = await parse("src/auth.py", b"def validate():\n return 'auth-v2'\ndef added(): pass\n")
                await save_parsed_ast_to_neo4j([changed], REPO, deleted_file_paths=["src/payments.py"])
                with sync_driver.session() as session:
                    names = session.run("MATCH (f:Function {repo_name: $repo}) RETURN collect(f.name) AS names", repo=REPO).single()["names"]
                    assert set(names) == {"validate", "added"}
                    assert session.run("MATCH (f:Function {repo_name: $repo})-[r:CALLS]->() RETURN count(r) AS n", repo=REPO).single()["n"] == 0
                    assert session.run("MATCH (u:UnresolvedCall {repo_name: $repo}) RETURN count(u) AS n", repo=REPO).single()["n"] == 0

                await save_parsed_ast_to_neo4j([payments], REPO, replace_existing=True)
                with sync_driver.session() as session:
                    assert session.run("MATCH (f:Function {repo_name: $repo}) RETURN collect(f.file_path) AS paths", repo=REPO).single()["paths"] == ["src/payments.py"]
        finally:
            await async_driver.close()

    asyncio.run(run())
