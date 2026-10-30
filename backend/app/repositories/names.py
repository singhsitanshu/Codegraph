"""Canonical GitHub repository names, validated where input enters the app.

Inner layers receive ``owner/repository`` strings that already passed through
this module and use them as-is.
"""

import re
from dataclasses import dataclass
from typing import Annotated, Self
from urllib.parse import unquote, urlparse

from pydantic import AfterValidator, BeforeValidator, StringConstraints, WithJsonSchema


GITHUB_REPOSITORY_PART = re.compile(r"[A-Za-z0-9_.-]+")
GITHUB_HOSTS = frozenset({"github.com", "www.github.com"})
MAX_REPOSITORY_NAME_LENGTH = 201
MAX_REPOSITORY_URL_LENGTH = 2_048


def normalize_repository_name(repo_name: str) -> str:
    """Validate and normalize an ``owner/repository`` identifier."""

    normalized = repo_name.strip().removesuffix(".git")
    parts = normalized.split("/")
    if (
        len(parts) != 2
        or not all(GITHUB_REPOSITORY_PART.fullmatch(part) for part in parts)
    ):
        raise ValueError("repo_name must use the 'owner/repository' format")
    return normalized


RepositoryName = Annotated[
    str,
    StringConstraints(max_length=MAX_REPOSITORY_NAME_LENGTH),
    AfterValidator(normalize_repository_name),
]
"""Canonical ``owner/repository`` key for request bodies, query and path params."""


@dataclass(frozen=True)
class GitHubRepository:
    """A validated GitHub repository split into its owner and name."""

    owner: str
    name: str

    @classmethod
    def from_full_name(cls, full_name: str) -> Self:
        """Parse an ``owner/repository`` identifier."""

        owner, name = normalize_repository_name(full_name).split("/")
        return cls(owner=owner, name=name)

    @classmethod
    def from_url(cls, url: str) -> Self:
        """Parse a canonical GitHub HTTPS repository URL."""

        parsed_url = urlparse(url.strip())
        if (
            parsed_url.scheme.lower() != "https"
            or parsed_url.hostname not in GITHUB_HOSTS
        ):
            raise ValueError("url must be an HTTPS github.com repository URL")
        return cls.from_full_name(unquote(parsed_url.path).strip("/"))

    @property
    def full_name(self) -> str:
        """The canonical ``owner/repository`` graph scope."""

        return f"{self.owner}/{self.name}"


def _repository_from_url(value: object) -> GitHubRepository:
    """Parse a request URL string into a validated repository."""

    if isinstance(value, GitHubRepository):
        return value
    if not isinstance(value, str):
        raise ValueError("url must be a string")
    if len(value) > MAX_REPOSITORY_URL_LENGTH:
        raise ValueError("url is too long")
    return GitHubRepository.from_url(value)


GitHubRepositoryUrl = Annotated[
    GitHubRepository,
    BeforeValidator(_repository_from_url),
    WithJsonSchema(
        {"type": "string", "format": "uri", "maxLength": MAX_REPOSITORY_URL_LENGTH}
    ),
]
"""A GitHub HTTPS repository URL, parsed into its owner and name."""
