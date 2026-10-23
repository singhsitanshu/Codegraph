"""Bounded webhook change sets and failure behavior."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.pipeline import _extract_push_changes, process_github_event


def payload(commits):
    return {
        "repository": {"full_name": "owner/repository", "name": "repository", "owner": {"login": "owner"}},
        "before": "a" * 40,
        "after": "b" * 40,
        "size": len(commits),
        "commits": commits,
    }


def test_change_set_tracks_final_path_state_and_supported_extensions():
    updated, deleted = _extract_push_changes(payload([
        {"added": ["src/new.py", "README.md"], "modified": ["src/old.py"], "removed": []},
        {"added": [], "modified": ["src/./new.py"], "removed": ["src/old.py"]},
    ]))
    assert updated == ["src/new.py"]
    assert deleted == ["src/old.py"]


@pytest.mark.parametrize("changes", [
    {"commits": [], "size": 0},
    {"commits": [{"added": ["a.py"], "modified": []}], "size": 1},
    {"commits": [{"added": [], "modified": [], "removed": []}], "size": 2},
    {"commits": [{"added": [], "modified": [], "removed": []}]},
    {"commits": [{"added": [], "modified": [], "removed": []}], "size": 1, "created": True},
    {"commits": [{"added": ["../escape.py"], "modified": [], "removed": []}], "size": 1},
])
def test_incomplete_or_unsafe_change_sets_are_rejected(changes):
    with pytest.raises((ValueError, TypeError)):
        _extract_push_changes(changes)


def test_fetch_failure_does_not_update_graph():
    event = payload([{"added": ["src/a.py"], "modified": [], "removed": []}])
    save = AsyncMock()
    with (
        patch("app.services.pipeline.fetch_raw_file_content", new=AsyncMock(side_effect=RuntimeError("fetch failed"))),
        patch("app.services.pipeline.save_parsed_ast_to_neo4j", new=save),
    ):
        asyncio.run(process_github_event(event, "push"))
    save.assert_not_awaited()


def test_removed_file_is_passed_to_incremental_writer():
    event = payload([{"added": [], "modified": [], "removed": ["src/old.py"]}])
    save = AsyncMock()
    with patch("app.services.pipeline.save_parsed_ast_to_neo4j", new=save):
        asyncio.run(process_github_event(event, "push"))
    save.assert_awaited_once_with([], repo_name="owner/repository", deleted_file_paths=["src/old.py"])
