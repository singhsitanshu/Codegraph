"""Versioned, repository-scoped identities for parsed function definitions.

These are application keys, not Neo4j element IDs. Persistence will adopt them
in CG-002B; the current database writer deliberately continues using its old
schema until that migration is ready.
"""

import hashlib
import json
import re


_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def normalize_repository_path(file_path: str) -> str:
    """Return a POSIX repository-relative path, rejecting paths outside the root."""

    path = file_path.replace("\\", "/")
    if not path or path.startswith("/") or _DRIVE_PREFIX.match(path):
        raise ValueError("file_path must be repository-relative")
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ValueError("file_path escapes the repository root")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise ValueError("file_path must identify a file")
    return "/".join(parts)


def generate_function_entity_id(
    repository: str,
    file_path: str,
    language: str,
    qualified_name: str,
    discriminator: str,
) -> str:
    """Hash a canonical function key with an explicit schema version.

    Text fields preserve case because identifiers and paths can be case-sensitive.
    Only surrounding whitespace and path separators/dot segments are normalized.
    """

    fields = (
        repository.strip(),
        normalize_repository_path(file_path),
        language.strip().lower(),
        qualified_name.strip(),
        discriminator.strip(),
    )
    if not all(fields):
        raise ValueError("function identity fields must not be blank")
    encoded = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"fn:v1:{digest}"
