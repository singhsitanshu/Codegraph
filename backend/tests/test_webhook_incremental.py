"""Bounded webhook change sets, boundary parsing, and failure behavior."""

import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.repositories.names import GitHubRepository
from app.webhooks.github_events import PushChangeSet, parse_push_change_set
from app.webhooks.pipeline import process_push_change_set


REPOSITORY = GitHubRepository(owner="owner", name="repository")


def payload(commits, **overrides):
    return {
        "repository": {"full_name": "owner/repository", "name": "repository", "owner": {"login": "owner"}},
        "before": "a" * 40,
        "after": "b" * 40,
        "size": len(commits),
        "commits": commits,
        **overrides,
    }


def change_set(updated=(), deleted=()):
    return PushChangeSet(
        repository=REPOSITORY,
        commit_sha="b" * 40,
        updated_paths=list(updated),
        deleted_paths=list(deleted),
    )


def post_webhook(body, event="push"):
    raw_body = body if isinstance(body, bytes) else json.dumps(body).encode()
    digest = hmac.new(settings.GITHUB_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return TestClient(app).post(
        "/api/webhooks/github",
        content=raw_body,
        headers={"X-GitHub-Event": event, "X-Hub-Signature-256": f"sha256={digest}"},
    )


def test_change_set_tracks_final_path_state_and_supported_extensions():
    parsed = parse_push_change_set(payload([
        {"added": ["src/new.py", "README.md"], "modified": ["src/old.py"], "removed": []},
        {"added": [], "modified": ["src/./new.py"], "removed": ["src/old.py"]},
    ]))
    assert parsed == PushChangeSet(
        repository=REPOSITORY,
        commit_sha="b" * 40,
        updated_paths=["src/new.py"],
        deleted_paths=["src/old.py"],
    )


def test_change_set_skips_ignored_directories_like_full_ingestion():
    parsed = parse_push_change_set(payload([
        {
            "added": ["node_modules/pkg/index.js", "src/dist.py"],
            "modified": ["build/generated.py", "src/app.py"],
            "removed": [".venv/lib/site.py"],
        },
    ]))
    assert parsed.updated_paths == ["src/app.py", "src/dist.py"]
    assert parsed.deleted_paths == []


def test_change_set_falls_back_to_full_name_for_repository():
    event = payload([{"added": [], "modified": [], "removed": []}])
    event["repository"] = {"full_name": "owner/repository"}
    assert parse_push_change_set(event).repository == REPOSITORY


@pytest.mark.parametrize("changes", [
    {"commits": [], "size": 0},
    {"commits": [{"added": ["a.py"], "modified": []}], "size": 1},
    {"commits": [{"added": [], "modified": [], "removed": []}], "size": 2},
    {"commits": [{"added": [], "modified": [], "removed": []}], "size": True},
    {"commits": [{"added": [], "modified": [], "removed": []}] * 20, "size": 20},
    {"commits": [{"added": [], "modified": [], "removed": []}], "size": 1, "created": True},
    {"commits": [{"added": [], "modified": [], "removed": []}], "size": 1, "before": "0" * 40},
    {"commits": [{"added": ["../escape.py"], "modified": [], "removed": []}], "size": 1},
    {"commits": [{"added": [], "modified": [], "removed": []}], "size": 1, "repository": {"name": "repository"}},
])
def test_incomplete_or_unsafe_change_sets_are_rejected(changes):
    with pytest.raises(ValueError):
        parse_push_change_set({**payload([]), **changes})


def test_webhook_hands_validated_change_set_to_background_task():
    process = AsyncMock()
    with patch("app.webhooks.routes.process_push_change_set", new=process):
        response = post_webhook(payload([{"added": ["src/a.py"], "modified": [], "removed": []}]))

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    process.assert_awaited_once_with(change_set(updated=["src/a.py"]))


@pytest.mark.parametrize(("body", "event"), [
    (payload([{"added": ["src/a.py"], "modified": [], "removed": []}]), "pull_request"),
    (payload([{"added": ["src/a.py"], "modified": []}]), "push"),
    (payload([{"added": ["README.md"], "modified": [], "removed": []}]), "push"),
])
def test_webhook_acknowledges_unsupported_events_without_processing(body, event):
    process = AsyncMock()
    with patch("app.webhooks.routes.process_push_change_set", new=process):
        response = post_webhook(body, event=event)

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert response.json()["reason"]
    process.assert_not_awaited()


@pytest.mark.parametrize("body", [b"not json", b"[]"])
def test_webhook_rejects_bodies_that_are_not_json_objects(body):
    assert post_webhook(body).status_code == 400


def test_webhook_rejects_invalid_signature():
    response = TestClient(app).post(
        "/api/webhooks/github",
        content=b"{}",
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": "sha256=invalid"},
    )
    assert response.status_code == 401


def test_fetch_failure_does_not_update_graph():
    save = AsyncMock()
    with (
        patch("app.webhooks.pipeline.fetch_raw_file_content", new=AsyncMock(side_effect=RuntimeError("fetch failed"))),
        patch("app.webhooks.pipeline.ingest_identified_files", new=save),
    ):
        asyncio.run(process_push_change_set(change_set(updated=["src/a.py"])))
    save.assert_not_awaited()


def test_removed_file_is_passed_to_incremental_writer():
    save = AsyncMock()
    with patch("app.webhooks.pipeline.ingest_identified_files", new=save):
        asyncio.run(process_push_change_set(change_set(deleted=["src/old.py"])))
    save.assert_awaited_once_with([], repo_name="owner/repository", deleted_file_paths=["src/old.py"])
