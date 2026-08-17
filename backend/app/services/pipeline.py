import asyncio
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx

from app.db.graph_ops import save_parsed_ast_to_neo4j
from app.services.github_service import fetch_raw_file_content
from app.services.parser_service import CodeParser


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


def _extract_repository(payload: dict[str, Any]) -> tuple[str, str] | None:
    """Extract repository owner and name from a GitHub webhook payload."""

    repository = payload.get("repository")
    if not isinstance(repository, dict):
        return None

    repo = repository.get("name")
    owner_data = repository.get("owner")
    owner: object = None
    if isinstance(owner_data, dict):
        owner = owner_data.get("login") or owner_data.get("name")

    full_name = repository.get("full_name")
    if isinstance(full_name, str) and "/" in full_name:
        full_name_owner, full_name_repo = full_name.split("/", 1)
        owner = owner or full_name_owner
        repo = repo or full_name_repo

    if not isinstance(owner, str) or not owner:
        return None
    if not isinstance(repo, str) or not repo:
        return None
    return owner, repo


def _extract_commit_sha(payload: dict[str, Any], event_type: str) -> str | None:
    """Extract the immutable revision containing the changed files."""

    if event_type == "push":
        after = payload.get("after")
        if isinstance(after, str) and after:
            return after
        head_commit = payload.get("head_commit")
        if isinstance(head_commit, dict):
            commit_id = head_commit.get("id")
            return commit_id if isinstance(commit_id, str) and commit_id else None

    if event_type == "pull_request":
        pull_request = payload.get("pull_request")
        if isinstance(pull_request, dict):
            head = pull_request.get("head")
            if isinstance(head, dict):
                sha = head.get("sha")
                return sha if isinstance(sha, str) and sha else None
    return None


async def process_github_event(payload: dict[str, Any], event_type: str) -> None:
    """Orchestrate code-graph processing after the webhook is acknowledged."""

    normalized_event = event_type.strip().lower()
    logger.info("Starting GitHub event processing: event_type=%s", normalized_event)

    try:
        if normalized_event == "push":
            modified_files = _extract_push_files(payload)
        elif normalized_event == "pull_request":
            modified_files = _extract_pull_request_files(payload)
            if not modified_files:
                logger.info(
                    "The pull_request webhook did not embed filenames; a later "
                    "pipeline stage should retrieve them from GitHub's files API"
                )
        else:
            modified_files = []
            logger.info(
                "No file extractor configured for event_type=%s", normalized_event
            )

        logger.info(
            "Extracted %d changed file(s): %s",
            len(modified_files),
            modified_files,
        )

        repository = _extract_repository(payload)
        commit_sha = _extract_commit_sha(payload, normalized_event)
        if repository is None or commit_sha is None:
            logger.warning(
                "Skipping GitHub event because repository metadata or commit SHA "
                "is missing: event_type=%s",
                normalized_event,
            )
            return

        owner, repo = repository
        code_parser = CodeParser()

        async def fetch_and_parse(
            file_path: str,
        ) -> dict[str, str | list[str]] | None:
            try:
                code_parser.get_parser(Path(file_path).suffix)
            except ValueError as exc:
                logger.warning(
                    "Skipping unsupported source file %s: %s", file_path, exc
                )
                return None

            try:
                source_code = await fetch_raw_file_content(
                    owner,
                    repo,
                    file_path,
                    commit_sha,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == httpx.codes.NOT_FOUND:
                    logger.info(
                        "Skipping missing or deleted GitHub file at %s: %s",
                        commit_sha,
                        file_path,
                    )
                else:
                    logger.warning(
                        "GitHub returned %d while fetching %s",
                        exc.response.status_code,
                        file_path,
                    )
                return None
            except httpx.RequestError as exc:
                logger.warning("Unable to fetch GitHub file %s: %s", file_path, exc)
                return None

            try:
                return await code_parser.parse_file(
                    file_path,
                    source_code.encode("utf-8"),
                )
            except Exception as exc:
                logger.warning(
                    "Tree-sitter failed to parse GitHub file %s: %s",
                    file_path,
                    exc,
                    exc_info=True,
                )
                return None

        parsed_results = await asyncio.gather(
            *(fetch_and_parse(file_path) for file_path in modified_files)
        )
        parsed_relationships = [
            result for result in parsed_results if result is not None
        ]
        logger.info(
            "Tree-sitter stage complete: parsed %d of %d changed file(s)",
            len(parsed_relationships),
            len(modified_files),
        )

        await save_parsed_ast_to_neo4j(parsed_relationships)
        logger.info(
            "Neo4j stage complete: persisted %d parsed file(s)",
            len(parsed_relationships),
        )

        await asyncio.sleep(0)
        logger.info(
            "LangGraph/Claude stage placeholder: analyze blast radius for files=%s",
            modified_files,
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
