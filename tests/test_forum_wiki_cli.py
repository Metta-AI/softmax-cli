from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest
from typer.testing import CliRunner

from softmax.cli import app
from softmax.forum_wiki_api import (
    PostFeedPage,
    PostPublic,
    WikiEditConflictDetail,
    WikiEditConflictResponse,
    WikiPagePublic,
)

POST = {
    "id": "post_1",
    "title": "Hello",
    "author": {"type": "user", "user_id": "usr_1", "name": "Ada"},
    "page": "main",
    "content_format": "markdown",
    "body": "Body",
    "media": [],
    "created_at": "2026-08-29T00:00:00Z",
    "score": 1,
    "vote_count": 1,
}
PAGE = {
    "id": "wpg_1",
    "wiki_id": "wiki_1",
    "slug": "guide/start",
    "title": "Start",
    "current_revision_id": "wrv_1",
    "created_at": "2026-08-29T00:00:00Z",
    "current_revision": {
        "id": "wrv_1",
        "page_id": "wpg_1",
        "body": "Base",
        "author": {"type": "user", "user_id": "usr_1", "name": "Ada"},
        "note": None,
        "parent_revision_id": None,
        "created_at": "2026-08-29T00:00:00Z",
    },
}


class FakeApi:
    def __enter__(self) -> "FakeApi":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def list_forum(self, *_: object, **__: object) -> PostFeedPage:
        return PostFeedPage(entries=[PostPublic.model_validate(POST)], next_cursor=None)

    def read_wiki_page(self, *_: object, **__: object) -> WikiPagePublic:
        return WikiPagePublic.model_validate(PAGE)

    def edit_wiki_page(self, *_: object, **__: object) -> WikiEditConflictResponse:
        return WikiEditConflictResponse(
            detail=WikiEditConflictDetail(
                current_revision_id="wrv_2",
                current_body="Current body",
            )
        )


@pytest.fixture(autouse=True)
def _fake_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("softmax.forum.ForumWikiApi.from_current_token", lambda server: FakeApi())
    monkeypatch.setattr("softmax.wiki.ForumWikiApi.from_current_token", lambda server: FakeApi())


def test_help_documents_token_identity_and_has_no_impersonation_flag() -> None:
    for subapp in ("forum", "wiki"):
        result = CliRunner().invoke(app, [subapp, "--help"])
        assert result.exit_code == 0, result.output
        assert "active token" in result.output
        assert "--as" not in result.output


def test_vote_help_renders_numeric_values() -> None:
    result = CliRunner().invoke(app, ["forum", "vote", "--help"])

    assert result.exit_code == 0, result.output
    assert "-1, 0, or 1" in result.output


def test_forum_list_json_is_scriptable() -> None:
    result = CliRunner().invoke(app, ["forum", "list", "global", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["entries"][0]["id"] == "post_1"


def test_wiki_edit_conflict_writes_three_files_and_prints_merge_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    proposed = tmp_path / "proposed-input.md"
    proposed.write_text("Proposed body")
    conflict_dir = tmp_path / "conflict"

    def make_conflict_dir(*_: object, **__: object) -> str:
        conflict_dir.mkdir()
        return str(conflict_dir)

    monkeypatch.setattr("softmax.wiki.tempfile.mkdtemp", make_conflict_dir)

    result = CliRunner().invoke(
        app,
        [
            "wiki",
            "edit",
            "global",
            "guide/start",
            "--file",
            str(proposed),
            "--title",
            "Guide's start",
            "--note",
            "Resolve conflict; keep examples",
        ],
    )

    assert result.exit_code != 0
    assert (conflict_dir / "base.md").read_text() == "Base"
    assert (conflict_dir / "current.md").read_text() == "Current body"
    assert (conflict_dir / "proposed.md").read_text() == "Proposed body"
    assert "git merge-file" in result.output
    assert str(conflict_dir / "proposed.md") in result.output
    retry_command = next(line for line in result.output.splitlines() if line.startswith("softmax wiki edit"))
    assert shlex.split(retry_command) == [
        "softmax",
        "wiki",
        "edit",
        "global",
        "guide/start",
        "--file",
        str(conflict_dir / "proposed.md"),
        "--server",
        "https://softmax.com/api",
        "--title",
        "Guide's start",
        "--note",
        "Resolve conflict; keep examples",
    ]
