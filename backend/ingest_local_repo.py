"""Ingest the local Requests source tree into the Neo4j code graph."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from app.db import close_neo4j_driver
from app.db.graph_ops import save_parsed_ast_to_neo4j
from app.db.neo4j_client import driver
from app.services.parser_service import parse_changed_files


TARGET_REPO_PATH = "/Users/sitanshusingh/Downloads/requests"
IGNORED_DIRECTORIES = frozenset(
    {".git", "__pycache__", "venv", ".venv", "build", "tests", "docs"}
)
NODE_COUNT_QUERY = "MATCH (n) RETURN labels(n) AS type, count(n) AS count"


def discover_python_files(repo_path: str) -> list[str]:
    """Return sorted Python files beneath ``repo_path``, excluding non-core trees."""
    files_to_parse: list[str] = []

    for root, directory_names, file_names in os.walk(repo_path):
        directory_names[:] = sorted(
            name for name in directory_names if name not in IGNORED_DIRECTORIES
        )
        for file_name in sorted(file_names):
            if file_name.endswith(".py"):
                files_to_parse.append(os.path.join(root, file_name))

    files_to_parse.sort()
    return files_to_parse


def verify_ingestion() -> list[dict[str, Any]]:
    """Query Neo4j node counts by label and return JSON-like records."""
    if driver is None:
        raise RuntimeError(
            "Neo4j is unavailable. Check NEO4J_URI, NEO4J_USER, and "
            "NEO4J_PASSWORD before running ingestion."
        )

    with driver.session() as session:
        return session.run(NODE_COUNT_QUERY).data()


async def ingest_repository() -> None:
    """Discover, parse, persist, and verify the configured local repository."""
    if not os.path.isdir(TARGET_REPO_PATH):
        raise FileNotFoundError(
            f"Target repository does not exist: {TARGET_REPO_PATH}"
        )

    files_to_parse = discover_python_files(TARGET_REPO_PATH)
    print(f"Discovered {len(files_to_parse)} Python files in {TARGET_REPO_PATH}")
    if not files_to_parse:
        raise RuntimeError("No Python files were discovered; ingestion aborted")

    parsed_data = await parse_changed_files(files_to_parse)
    print(f"Successfully parsed {len(parsed_data)} Python files")
    if not parsed_data:
        raise RuntimeError("Tree-sitter produced no parsed data; ingestion aborted")

    await save_parsed_ast_to_neo4j(parsed_data)
    print(f"Persisted AST data for {len(parsed_data)} files")

    counts = await asyncio.to_thread(verify_ingestion)
    print("Neo4j node counts:")
    for record in counts:
        print(f"  {record['type']}: {record['count']}")


async def main() -> int:
    """Run ingestion and return a shell-compatible status code."""
    try:
        await ingest_repository()
    except Exception as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1
    finally:
        await close_neo4j_driver()
        if driver is not None:
            driver.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
