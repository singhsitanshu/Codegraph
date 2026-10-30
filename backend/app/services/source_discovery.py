"""Which repository files are ingested as source code.

A file is ingested when its extension belongs to a supported language and no
directory on its path is a dependency, build, cache, or VCS directory. Full
ingestion and push webhooks both apply this rule.
"""

import os
from pathlib import Path, PurePosixPath

from app.services.languages import SUPPORTED_EXTENSIONS


IGNORED_REPOSITORY_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)


def _has_supported_extension(file_name: str) -> bool:
    return Path(file_name).suffix.lower() in SUPPORTED_EXTENSIONS


def is_repository_source_path(path: str) -> bool:
    """Return whether a repository-relative POSIX path is ingested."""

    *directories, file_name = PurePosixPath(path).parts
    return _has_supported_extension(file_name) and not any(
        directory in IGNORED_REPOSITORY_DIRECTORIES for directory in directories
    )


def discover_repository_source_files(repository_root: Path) -> list[str]:
    """Walk a checked-out repository and return its ingested source file paths."""

    source_files: list[str] = []
    for root, directory_names, file_names in os.walk(repository_root):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in IGNORED_REPOSITORY_DIRECTORIES
        )
        for file_name in sorted(file_names):
            if _has_supported_extension(file_name):
                source_files.append(str(Path(root, file_name)))
    return source_files
