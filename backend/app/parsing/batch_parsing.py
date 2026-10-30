"""Read, token-count and parse batches of source files concurrently."""

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from app.parsing.parse_results import ParsedBatch, ParsedFileProgress, ParsedSource
from app.parsing.parser import CodeParser
from app.tokens import count_tokens


logger = logging.getLogger(__name__)
MAX_CONCURRENT_FILE_READS = 32


async def parse_changed_files_with_progress(
    file_paths: list[str],
) -> AsyncIterator[ParsedFileProgress]:
    """Parse files concurrently and yield once whenever a file completes.

    Failed files yield a progress item whose ``result`` is ``None``. This lets
    streaming callers advance their progress bar without persisting bad input.
    The ``index`` field lets batch callers restore the input ordering even
    though files can complete out of order.
    """

    total = len(file_paths)
    if total == 0:
        return

    code_parser = CodeParser()
    file_read_slots = asyncio.Semaphore(MAX_CONCURRENT_FILE_READS)

    async def parse_path(
        index: int,
        file_path: str,
    ) -> tuple[int, ParsedSource | None, int]:
        path = Path(file_path)
        source_tokens = 0
        try:
            async with file_read_slots:
                source_code = await asyncio.to_thread(path.read_bytes)
                source_text = source_code.decode("utf-8", errors="replace")
                source_tokens = await asyncio.to_thread(
                    count_tokens,
                    source_text,
                )
                result = await code_parser.parse_file(file_path, source_code)
            return index, result, source_tokens
        except FileNotFoundError:
            logger.info("Skipping missing or deleted source file: %s", file_path)
        except UnicodeDecodeError as exc:
            logger.warning("Skipping source file %s: %s", file_path, exc)
        except OSError as exc:
            logger.warning("Unable to read source file %s: %s", file_path, exc)
        except ValueError as exc:
            logger.warning("Skipping unsupported source file %s: %s", file_path, exc)
        except Exception as exc:
            logger.warning(
                "Tree-sitter failed to parse source file %s: %s",
                file_path,
                exc,
                exc_info=True,
            )
        return index, None, source_tokens

    tasks = [
        asyncio.create_task(parse_path(index, file_path))
        for index, file_path in enumerate(file_paths)
    ]
    try:
        for processed, completed_task in enumerate(
            asyncio.as_completed(tasks),
            start=1,
        ):
            index, result, source_tokens = await completed_task
            yield ParsedFileProgress(
                index=index,
                processed=processed,
                total=total,
                source_tokens=source_tokens,
                result=result,
            )
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def parse_changed_files(file_paths: list[str]) -> ParsedBatch:
    """Parse source files, keeping successful results in input order."""

    parsed_by_index: dict[int, ParsedSource] = {}
    source_tokens = 0
    async for progress in parse_changed_files_with_progress(file_paths):
        source_tokens += progress.source_tokens
        if progress.result is not None:
            parsed_by_index[progress.index] = progress.result
    return ParsedBatch(
        files=[parsed_by_index[index] for index in sorted(parsed_by_index)],
        source_tokens=source_tokens,
    )
