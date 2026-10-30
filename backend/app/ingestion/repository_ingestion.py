"""Full ingestion of a public GitHub repository into its code graph.

The repository is downloaded, its source files are discovered, parsed and
identified by repository-relative path, and the graph is rebuilt from them.
Each step is reported as an event; the last event is always either
:class:`IngestionComplete` or :class:`IngestionFailed`.
"""

import asyncio
import logging
import zipfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.database.errors import NEO4J_ERRORS, Neo4jFailureDetails
from app.ingestion import ingestion_progress
from app.ingestion.github_download import download_and_extract_repo
from app.ingestion.graph_ingestion import (
    IngestionProgress,
    ingest_identified_files_with_progress,
)
from app.ingestion.source_discovery import discover_repository_source_files
from app.parsing.batch_parsing import parse_changed_files_with_progress
from app.parsing.parse_results import IdentifiedFile, ParsedSource
from app.parsing.source_identity import identify_parsed_source
from app.repositories.names import GitHubRepository


logger = logging.getLogger(__name__)

REPOSITORY_INGESTION_FAILURES = Neo4jFailureDetails(
    authentication="Neo4j authentication failed during repository ingestion",
    unavailable="Neo4j is unavailable during repository ingestion",
    failure="Neo4j repository ingestion failed",
)


@dataclass(frozen=True, slots=True)
class IngestionFailed:
    """Ingestion stopped at ``progress`` for the client-facing ``error``."""

    progress: int
    error: str


@dataclass(frozen=True, slots=True)
class IngestionComplete:
    """The repository graph was rebuilt with this full-source token baseline."""

    repo_name: str
    total_repo_tokens: int


RepositoryIngestionEvent = IngestionProgress | IngestionFailed | IngestionComplete


def identify_repository_files(
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


async def ingest_github_repository(
    repository: GitHubRepository,
) -> AsyncIterator[RepositoryIngestionEvent]:
    """Rebuild one repository's graph while reporting each step."""

    canonical_repo_name = repository.full_name
    current_progress = 0
    try:
        current_progress = ingestion_progress.DOWNLOAD_STARTED
        yield IngestionProgress("Downloading repository...", current_progress)
        async with download_and_extract_repo(
            repository.owner,
            repository.name,
        ) as extracted_root:
            current_progress = ingestion_progress.DOWNLOADED
            yield IngestionProgress(
                "Repository downloaded and extracted.",
                current_progress,
            )
            source_files = await asyncio.to_thread(
                discover_repository_source_files,
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
                    yield IngestionProgress(
                        f"Parsing files ({file_progress.processed}/"
                        f"{file_progress.total})...",
                        current_progress,
                    )
            else:
                current_progress = ingestion_progress.PARSING.end
                yield IngestionProgress(
                    "No supported source files found.",
                    current_progress,
                )

            if len(parsed_by_index) != len(source_files):
                logger.warning(
                    "Aborting full ingest for %s because a supported source file "
                    "could not be parsed",
                    canonical_repo_name,
                )
                yield IngestionFailed(
                    current_progress,
                    "A supported source file could not be parsed",
                )
                return

            identified_files = identify_repository_files(
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
            yield IngestionProgress("Batching data to Neo4j...", current_progress)
            async for graph_progress in ingest_identified_files_with_progress(
                identified_files,
                repo_name=canonical_repo_name,
                replace_existing=True,
                total_repo_tokens=total_repo_tokens,
            ):
                current_progress = graph_progress.progress
                yield graph_progress

            yield IngestionComplete(canonical_repo_name, total_repo_tokens)
    except httpx.HTTPStatusError as exc:
        response_status = exc.response.status_code
        if response_status == httpx.codes.NOT_FOUND:
            detail = "GitHub repository was not found"
        else:
            detail = f"GitHub archive download failed with status {response_status}"
        logger.warning("Unable to ingest %s: %s", canonical_repo_name, detail)
        yield IngestionFailed(current_progress, detail)
    except (httpx.RequestError, zipfile.BadZipFile, ValueError) as exc:
        logger.warning("Unable to download or extract %s: %s", canonical_repo_name, exc)
        yield IngestionFailed(
            current_progress,
            "GitHub repository download or extraction failed",
        )
    except NEO4J_ERRORS as exc:
        yield IngestionFailed(
            current_progress,
            REPOSITORY_INGESTION_FAILURES.describe(exc),
        )
    except Exception:
        logger.exception("Unexpected repository ingestion failure")
        yield IngestionFailed(
            current_progress,
            "Unexpected repository ingestion failure",
        )
