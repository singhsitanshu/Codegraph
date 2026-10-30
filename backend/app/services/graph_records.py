"""Graph records derived from identified source files.

Identified files are flattened into the File and Function records the graph
stores, and each function's call names are resolved to the definitions they
refer to. Records are plain dicts shaped like the persistence layer's query
parameters; nothing here touches the database.
"""

import logging
from collections.abc import Iterable
from typing import Any

from app.services.parse_results import IdentifiedFile, IdentifiedFunction


logger = logging.getLogger(__name__)


def _function_record(
    function: IdentifiedFunction,
    parsed_file: IdentifiedFile,
) -> dict[str, Any]:
    """Build one persisted Function record keyed by its CG-002A identity."""

    return {
        "entity_id": function.entity_id,
        "name": function.name,
        "qualified_name": function.qualified_name,
        "file_path": parsed_file.file_path,
        "language": parsed_file.language,
        "signature": function.signature,
        "definition_discriminator": function.definition_discriminator,
        "start_line": function.start_line,
        "end_line": function.end_line,
        "start_column": function.start_column,
        "end_column": function.end_column,
        "raw_code": function.raw_code,
    }


def extract_graph_records(
    parsed_files: list[IdentifiedFile],
    repo_name: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], dict[str, list[str]]]:
    """Flatten identified files into File records, Function records, and call names.

    The third value maps each caller ``entity_id`` to the callee names the
    parser attributed to that function's body, in source order.
    """

    files: list[dict[str, str]] = []
    functions: list[dict[str, Any]] = []
    function_calls: dict[str, list[str]] = {}
    seen_files: set[str] = set()

    for parsed_file in parsed_files:
        if parsed_file.repository != repo_name:
            raise ValueError(
                f"{parsed_file.file_path} was identified for repository "
                f"{parsed_file.repository!r}, not {repo_name!r}"
            )
        if parsed_file.file_path not in seen_files:
            seen_files.add(parsed_file.file_path)
            files.append({"path": parsed_file.file_path})

        for function in parsed_file.functions:
            if function.entity_id in function_calls:
                logger.warning(
                    "Skipping duplicate function identity %s in %s",
                    function.qualified_name,
                    parsed_file.file_path,
                )
                continue
            functions.append(_function_record(function, parsed_file))
            function_calls[function.entity_id] = [
                call.name for call in function.calls
            ]

    return files, functions, function_calls


def _append_index(index: dict[Any, list[str]], key: Any, entity_id: str) -> None:
    index.setdefault(key, []).append(entity_id)


def resolve_calls(
    functions: list[dict[str, Any]],
    function_calls: dict[str, list[str]],
    definitions: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[str]]]:
    """Map call names to Function IDs without collapsing same-named definitions.

    A callee resolves to exactly one definition: first the nearest enclosing
    lexical scope in the caller's file, then a unique same-file name, then a
    unique repository-wide name. Names that never match become external calls;
    names with several equally plausible definitions are recorded as ambiguous
    on the caller instead of being linked to an arbitrary one.
    """

    by_scope: dict[tuple[str, str], list[str]] = {}
    by_file_name: dict[tuple[str, str], list[str]] = {}
    by_name: dict[str, list[str]] = {}
    for definition in definitions:
        entity_id = definition["entity_id"]
        file_path = definition["file_path"]
        name = definition["name"]
        _append_index(by_scope, (file_path, definition["qualified_name"]), entity_id)
        _append_index(by_file_name, (file_path, name), entity_id)
        _append_index(by_name, name, entity_id)

    def resolve(caller: dict[str, Any], name: str) -> tuple[list[str], str]:
        file_path = caller["file_path"]
        scope = caller["qualified_name"].split(".")
        for depth in range(len(scope), -1, -1):
            qualified_name = ".".join([*scope[:depth], name])
            matches = by_scope.get((file_path, qualified_name), [])
            if matches:
                return matches, "lexical_scope"
        matches = by_file_name.get((file_path, name), [])
        if matches:
            return matches, "same_file"
        return by_name.get(name, []), "repository_unique"

    internal: dict[tuple[str, str], dict[str, Any]] = {}
    external: dict[tuple[str, str], dict[str, Any]] = {}
    ambiguous: dict[str, list[str]] = {}
    for caller in functions:
        caller_id = caller["entity_id"]
        for name in function_calls.get(caller_id, []):
            matches, resolution = resolve(caller, name)
            if len(matches) > 1:
                names = ambiguous.setdefault(caller_id, [])
                if name not in names:
                    names.append(name)
                continue
            if matches:
                key = (caller_id, matches[0])
                record = internal.setdefault(
                    key,
                    {
                        "caller_id": caller_id,
                        "target_id": matches[0],
                        "resolution": resolution,
                        "call_count": 0,
                        "file_path": caller["file_path"],
                    },
                )
            else:
                key = (caller_id, name)
                record = external.setdefault(
                    key,
                    {
                        "caller_id": caller_id,
                        "target_name": name,
                        "call_count": 0,
                        "file_path": caller["file_path"],
                    },
                )
            record["call_count"] += 1

    return list(internal.values()), list(external.values()), ambiguous
