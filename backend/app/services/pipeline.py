import asyncio
import logging
from pathlib import Path
from typing import Any

from app.db.graph_ops import save_parsed_ast_to_neo4j
from app.services.github_service import fetch_raw_file_content
from app.services.parser_service import (
    SUPPORTED_EXTENSIONS,
    CodeParser,
    attach_function_entity_ids,
)
from app.utils.entity_identity import normalize_repository_path


logger = logging.getLogger(__name__)


def _extract_push_changes(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Require a complete, bounded commit list before changing a graph."""

    commits = payload.get("commits")
    reported_size = payload.get("size")
    before = payload.get("before")
    after = payload.get("after")
    if (
        not isinstance(commits, list)
        or not commits
        or len(commits) >= 20
        or not isinstance(reported_size, int)
        or isinstance(reported_size, bool)
        or reported_size != len(commits)
        or payload.get("forced") is True
        or payload.get("created") is True
        or payload.get("deleted") is True
        or not isinstance(before, str)
        or not before
        or set(before) == {"0"}
        or not isinstance(after, str)
        or not after
        or set(after) == {"0"}
    ):
        raise ValueError("push event does not contain a complete supported change set")
    updated: set[str] = set()
    deleted: set[str] = set()
    for commit in commits:
        if not isinstance(commit, dict) or any(
            not isinstance(commit.get(field), list)
            for field in ("added", "modified", "removed")
        ):
            raise ValueError("push commit is missing file change lists")
        for field in ("added", "modified"):
            for raw_path in commit[field]:
                path = normalize_repository_path(raw_path)
                if Path(path).suffix.lower() in SUPPORTED_EXTENSIONS:
                    updated.add(path)
                    deleted.discard(path)
        for raw_path in commit["removed"]:
            path = normalize_repository_path(raw_path)
            if Path(path).suffix.lower() in SUPPORTED_EXTENSIONS:
                deleted.add(path)
                updated.discard(path)
    return sorted(updated), sorted(deleted)


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
    return None


async def process_github_event(payload: dict[str, Any], event_type: str) -> None:
    """Orchestrate code-graph processing after the webhook is acknowledged."""

    normalized_event = event_type.strip().lower()
    logger.info("Starting GitHub event processing: event_type=%s", normalized_event)

    try:
        if normalized_event != "push":
            logger.info(
                "Skipping %s event: only complete push change sets support "
                "safe incremental ingestion",
                normalized_event,
            )
            return
        try:
            modified_files, deleted_files = _extract_push_changes(payload)
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping incomplete push change set: %s", exc)
            return
        if not modified_files and not deleted_files:
            logger.info("No supported source files changed in push event")
            return

        logger.info(
            "Extracted %d updated and %d deleted source file(s)",
            len(modified_files), len(deleted_files),
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

        async def fetch_and_parse(file_path: str) -> dict[str, Any]:
            source_code = await fetch_raw_file_content(
                owner, repo, file_path, commit_sha
            )
            parsed_file = await code_parser.parse_file(
                file_path, source_code.encode("utf-8")
            )
            return attach_function_entity_ids(
                parsed_file,
                repository=f"{owner}/{repo}",
                file_path=file_path,
            )

        parsed_results = await asyncio.gather(
            *(fetch_and_parse(file_path) for file_path in modified_files)
        )
        parsed_relationships = list(parsed_results)
        logger.info(
            "Tree-sitter stage complete: parsed %d of %d changed file(s)",
            len(parsed_relationships),
            len(modified_files),
        )

        await save_parsed_ast_to_neo4j(
            parsed_relationships,
            repo_name=f"{owner}/{repo}",
            deleted_file_paths=deleted_files,
        )
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
