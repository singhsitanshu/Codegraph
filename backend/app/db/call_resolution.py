"""Conservative resolution of parser call sites to persisted definitions.

Only an unqualified call to one same-file top-level or immediately nested
definition is linked. Such a link is explicitly inferred, never confirmed:
the parser does not perform binding or import analysis.
"""

import json
from collections import Counter, defaultdict
from typing import Any


class CallResolutionIndex:
    """Build repository lookups once instead of scanning definitions per call."""

    def __init__(self, definitions: list[dict[str, Any]]) -> None:
        self.name_counts: Counter[str] = Counter()
        self.local_bodies: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for function in definitions:
            self.name_counts[function["name"]] += 1
            if function.get("has_body", True):
                key = (
                    function["file_path"], function["name"],
                    function["qualified_name"],
                )
                self.local_bodies[key].append(function["entity_id"])


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
    index: CallResolutionIndex,
) -> tuple[str | None, str, str]:
    """Return target ID, status and evidence without guessing dynamic targets."""

    name = call["name"]
    if caller is not None and call["syntax"] == name:
        immediate_nested = index.local_bodies.get(
            (caller["file_path"], name, f"{caller['qualified_name']}.{name}"), ()
        )
        if len(immediate_nested) == 1:
            return immediate_nested[0], "inferred", "lexical_nested"
        if len(immediate_nested) > 1:
            return None, "ambiguous", "multiple_lexical_definitions"
        top_level = index.local_bodies.get((caller["file_path"], name, name), ())
        if len(top_level) == 1:
            return top_level[0], "inferred", "same_file_top_level"
        if len(top_level) > 1:
            return None, "ambiguous", "multiple_local_definitions"

    if index.name_counts[name] > 1:
        return None, "ambiguous", "multiple_matching_names"
    return None, "unresolved", "insufficient_binding_evidence"
