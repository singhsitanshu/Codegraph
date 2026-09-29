"""Conservative resolution of parser call sites to persisted definitions.

Only an unqualified call to one same-file top-level or immediately nested
definition is linked. Such a link is explicitly inferred, never confirmed:
the parser does not perform binding or import analysis.
"""

import json
from typing import Any


def call_site_id(file_path: str, caller_id: str | None, call: dict[str, Any]) -> str:
    """A deterministic location key for one syntactic call occurrence."""

    location = [
        file_path,
        caller_id or "",
        call["start_line"],
        call["start_column"],
        call["end_line"],
        call["end_column"],
    ]
    return "call:v1:" + json.dumps(location, ensure_ascii=False, separators=(",", ":"))


def resolve_call(
    caller: dict[str, Any] | None,
    call: dict[str, Any],
    definitions: list[dict[str, Any]],
) -> tuple[str | None, str, str]:
    """Return target ID, status and evidence without guessing dynamic targets."""

    name = call["name"]
    matches = [function for function in definitions if function["name"] == name]
    if caller is not None and call["syntax"] == name:
        file_matches = [
            function
            for function in matches
            if function["file_path"] == caller["file_path"]
            and function.get("has_body", True)
        ]
        immediate_nested = [
            function
            for function in file_matches
            if function["qualified_name"] == f"{caller['qualified_name']}.{name}"
        ]
        if len(immediate_nested) == 1:
            return immediate_nested[0]["entity_id"], "inferred", "lexical_nested"
        if len(immediate_nested) > 1:
            return None, "ambiguous", "multiple_lexical_definitions"
        top_level = [
            function for function in file_matches
            if function["qualified_name"] == name
        ]
        if len(top_level) == 1:
            return top_level[0]["entity_id"], "inferred", "same_file_top_level"
        if len(top_level) > 1:
            return None, "ambiguous", "multiple_local_definitions"

    if len(matches) > 1:
        return None, "ambiguous", "multiple_matching_names"
    return None, "unresolved", "insufficient_binding_evidence"
