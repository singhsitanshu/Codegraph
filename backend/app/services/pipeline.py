import asyncio
import logging
from collections.abc import Iterable
from typing import Any

from app.services.parser_service import parse_changed_files


logger = logging.getLogger(__name__)


def _unique_paths(paths: Iterable[object]) -> list[str]:
    """Return non-empty string paths in first-seen order."""

    return list(dict.fromkeys(path for path in paths if isinstance(path, str) and path))


def _extract_push_files(payload: dict[str, Any]) -> list[str]:
    commits = payload.get("commits", [])
    if not isinstance(commits, list):
        return []

    paths: list[object] = []
    for commit in commits:
        if not isinstance(commit, dict):
            continue
        for field in ("modified", "added"):
            values = commit.get(field, [])
            if isinstance(values, list):
                paths.extend(values)
    return _unique_paths(paths)


def _extract_pull_request_files(payload: dict[str, Any]) -> list[str]:
    """Extract filenames when a provider or test fixture embeds them in the PR."""

    pull_request = payload.get("pull_request", {})
    if not isinstance(pull_request, dict):
        return []

    paths: list[object] = []
    for field in ("modified", "added", "modified_files", "added_files"):
        values = pull_request.get(field, [])
        if isinstance(values, list):
            paths.extend(values)

    files = pull_request.get("files", [])
    if isinstance(files, list):
        for file_entry in files:
            if isinstance(file_entry, str):
                paths.append(file_entry)
            elif isinstance(file_entry, dict):
                paths.append(file_entry.get("filename"))

    return _unique_paths(paths)


async def process_github_event(payload: dict[str, Any], event_type: str) -> None:
    """Orchestrate code-graph processing after the webhook is acknowledged."""

    normalized_event = event_type.strip().lower()
    logger.info("Starting GitHub event processing: event_type=%s", normalized_event)

    try:
        if normalized_event == "push":
            changed_files = _extract_push_files(payload)
        elif normalized_event == "pull_request":
            changed_files = _extract_pull_request_files(payload)
            if not changed_files:
                logger.info(
                    "The pull_request webhook did not embed filenames; a later "
                    "pipeline stage should retrieve them from GitHub's files API"
                )
        else:
            changed_files = []
            logger.info("No file extractor configured for event_type=%s", normalized_event)

        logger.info(
            "Extracted %d changed file(s): %s",
            len(changed_files),
            changed_files,
        )

        parsed_relationships = await parse_changed_files(changed_files)
        logger.info(
            "Tree-sitter stage complete: parsed %d of %d changed file(s)",
            len(parsed_relationships),
            len(changed_files),
        )

        await asyncio.sleep(0)
        logger.info(
            "Neo4j stage placeholder: ingest parsed relationships=%s",
            parsed_relationships,
        )

        await asyncio.sleep(0)
        logger.info(
            "LangGraph/Claude stage placeholder: analyze blast radius for files=%s",
            changed_files,
        )
    except Exception:
        # BackgroundTasks execute after the response, so errors must be captured
        # and logged here rather than propagated back to the webhook sender.
        logger.exception(
            "Unexpected error while processing GitHub event: event_type=%s",
            normalized_event,
        )
        return

    logger.info("Completed GitHub event processing: event_type=%s", normalized_event)
