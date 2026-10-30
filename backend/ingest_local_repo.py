"""Ingest the local Requests source tree into the Neo4j code graph."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from app.db.driver import close_neo4j_driver, get_neo4j_driver
from app.services.batch_parsing import parse_changed_files
from app.services.graph_ingestion import ingest_identified_files
from app.services.source_identity import identify_parsed_source


TARGET_REPO_PATH = "/Users/sitanshusingh/Downloads/requests"
TARGET_REPO_NAME = "psf/requests"
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


async def verify_ingestion() -> list[dict[str, Any]]:
    """Query Neo4j node counts by label and return JSON-like records."""
    async with get_neo4j_driver().session() as session:
        result = await session.run(NODE_COUNT_QUERY)
        return await result.data()


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

    parsed_batch = await parse_changed_files(files_to_parse)
    if len(parsed_batch.files) != len(files_to_parse):
        raise RuntimeError(
            "Full ingestion aborted because a discovered source file could not be parsed"
        )
    repository_root = Path(TARGET_REPO_PATH).resolve()
    identified_files = [
        identify_parsed_source(
            parsed_source,
            repository=TARGET_REPO_NAME,
            file_path=Path(parsed_source.file_path)
            .resolve()
            .relative_to(repository_root)
            .as_posix(),
        )
        for parsed_source in parsed_batch.files
    ]
    print(f"Successfully parsed {len(identified_files)} Python files")
    if not identified_files:
        raise RuntimeError("Tree-sitter produced no parsed data; ingestion aborted")

    await ingest_identified_files(
        identified_files,
        repo_name=TARGET_REPO_NAME,
        replace_existing=True,
        total_repo_tokens=parsed_batch.source_tokens,
    )
    print(f"Persisted AST data for {len(identified_files)} files")

    counts = await verify_ingestion()
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

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
