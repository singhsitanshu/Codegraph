import asyncio
import logging
from typing import Any

from app.db.graph_ops import save_parsed_ast_to_neo4j
from app.services.github_events import PushChangeSet
from app.services.github_service import fetch_raw_file_content
from app.services.parser_service import CodeParser, attach_function_entity_ids


logger = logging.getLogger(__name__)


async def process_push_change_set(change_set: PushChangeSet) -> None:
    """Apply a validated push change set after the webhook is acknowledged."""

    repository = change_set.repository
    modified_files = change_set.updated_paths
    logger.info(
        "Starting push processing for %s: %d updated and %d deleted source file(s)",
        repository.full_name,
        len(modified_files),
        len(change_set.deleted_paths),
    )

    try:
        code_parser = CodeParser()

        async def fetch_and_parse(file_path: str) -> dict[str, Any]:
            source_code = await fetch_raw_file_content(
                repository.owner,
                repository.name,
                file_path,
                change_set.commit_sha,
            )
            parsed_file = await code_parser.parse_file(
                file_path, source_code.encode("utf-8")
            )
            return attach_function_entity_ids(
                parsed_file,
                repository=repository.full_name,
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
            repo_name=repository.full_name,
            deleted_file_paths=change_set.deleted_paths,
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
            "Unexpected error while processing push for %s",
            repository.full_name,
        )
        return

    logger.info("Completed push processing for %s", repository.full_name)
