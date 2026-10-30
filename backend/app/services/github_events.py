"""GitHub webhook payloads, parsed once at the webhook boundary.

The webhook route turns a signed JSON body into a :class:`PushChangeSet`, or
rejects it as unsupported, before acknowledging the delivery. Background
processing then works only with the validated change set.
"""

from dataclasses import dataclass
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    StrictInt,
    StringConstraints,
    model_validator,
)

from app.services.source_discovery import is_repository_source_path
from app.utils.entity_identity import normalize_repository_path
from app.utils.repository import GitHubRepository


# GitHub lists at most 20 commits in a push payload, so a list of 20 may be
# truncated and cannot be trusted as a complete change set.
MAX_COMPLETE_PUSH_COMMITS = 19


def _reject_zero_sha(sha: str) -> str:
    """Reject the all-zero SHA GitHub uses for created or deleted refs."""

    if set(sha) == {"0"}:
        raise ValueError("commit SHA must identify an existing revision")
    return sha


CommitSha = Annotated[
    str,
    StringConstraints(min_length=1),
    AfterValidator(_reject_zero_sha),
]
RepositoryPath = Annotated[str, AfterValidator(normalize_repository_path)]


class GitHubAccount(BaseModel):
    """Owner fields of a webhook ``repository`` object."""

    login: str | None = None
    name: str | None = None


class GitHubRepositoryPayload(BaseModel):
    """Identifying fields of a webhook ``repository`` object."""

    name: str | None = None
    full_name: str | None = None
    owner: GitHubAccount | None = None


def _repository_from_payload(value: object) -> GitHubRepository:
    """Resolve the canonical repository, falling back to ``full_name``."""

    if isinstance(value, GitHubRepository):
        return value
    payload = GitHubRepositoryPayload.model_validate(value)
    owner = payload.owner.login or payload.owner.name if payload.owner else None
    name = payload.name
    if payload.full_name is not None and "/" in payload.full_name:
        full_name_owner, full_name_repo = payload.full_name.split("/", 1)
        owner = owner or full_name_owner
        name = name or full_name_repo
    return GitHubRepository.from_full_name(f"{owner or ''}/{name or ''}")


class GitHubPushCommit(BaseModel):
    """File changes reported for one commit of a push."""

    added: list[RepositoryPath]
    modified: list[RepositoryPath]
    removed: list[RepositoryPath]


class GitHubPushEvent(BaseModel):
    """A ``push`` payload whose commit list is a complete, bounded change set."""

    repository: Annotated[GitHubRepository, BeforeValidator(_repository_from_payload)]
    before: CommitSha
    after: CommitSha
    size: StrictInt
    commits: list[GitHubPushCommit] = Field(
        min_length=1,
        max_length=MAX_COMPLETE_PUSH_COMMITS,
    )
    forced: bool = False
    created: bool = False
    deleted: bool = False

    @model_validator(mode="after")
    def require_complete_change_set(self) -> Self:
        """Reject pushes whose commits do not describe every file change."""

        if self.size != len(self.commits):
            raise ValueError("push size does not match its commit list")
        if self.forced or self.created or self.deleted:
            raise ValueError("forced, created, and deleted pushes are not supported")
        return self


@dataclass(frozen=True)
class PushChangeSet:
    """Supported source files changed by one push, at an immutable revision."""

    repository: GitHubRepository
    commit_sha: str
    updated_paths: list[str]
    deleted_paths: list[str]


def parse_push_change_set(payload: dict[str, Any]) -> PushChangeSet:
    """Validate a push payload and reduce its commits to final file states.

    Raises:
        ValueError: If the payload is not a complete, supported push change
            set. Pydantic's ``ValidationError`` is a ``ValueError`` subclass.
    """

    event = GitHubPushEvent.model_validate(payload)
    updated: set[str] = set()
    deleted: set[str] = set()
    for commit in event.commits:
        for path in (*commit.added, *commit.modified):
            if is_repository_source_path(path):
                updated.add(path)
                deleted.discard(path)
        for path in commit.removed:
            if is_repository_source_path(path):
                deleted.add(path)
                updated.discard(path)
    return PushChangeSet(
        repository=event.repository,
        commit_sha=event.after,
        updated_paths=sorted(updated),
        deleted_paths=sorted(deleted),
    )
