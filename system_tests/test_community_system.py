import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest

from softmax_client.credentials import save_user_token
from softmax_client.forum_wiki import ForumWikiClient, WikiEditConflictResponse, WikiEditPublic


@pytest.mark.skipif("SOFTMAX_CLIENT_SYSTEM_URL" not in os.environ, reason="requires an isolated local Softmax stack")
def test_community_identity_idempotency_and_revision_conflicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = os.environ["SOFTMAX_CLIENT_SYSTEM_URL"].rstrip("/")
    assert urlsplit(server).hostname in {"localhost", "127.0.0.1", "::1"}
    marker = uuid4().hex
    user_id = f"client-{marker}"
    token = f"debug:{user_id}:{user_id}@example.com:true:Client System"
    monkeypatch.setenv("SOFTMAX_CONFIG_DIR", str(tmp_path / "credentials"))
    save_user_token(server=server, token=token)

    with ForumWikiClient.from_current_token(server) as client:
        post = client.create_post(title=marker, body="Community client proof", idempotency_key=marker)
        assert client.create_post(title=marker, body="Community client proof", idempotency_key=marker).id == post.id
        assert post.author.type == "user" and post.author.user_id == user_id
        assert "Community client proof" in client.read_post(post.id)
        assert post.id in {entry.id for entry in client.list_forum("softmax", sort="new").entries}
        assert client.search_forum(marker, forum_slug="softmax").entries[0].post.id == post.id
        assert client.search_forum(marker).entries[0].post.id == post.id
        comment = client.create_comment(post.id, body="Reply", idempotency_key=f"comment-{marker}")
        assert client.create_comment(post.id, body="Reply", idempotency_key=f"comment-{marker}").id == comment.id
        assert client.vote(post.id, value=1).score == 1
        assert client.vote(post.id, comment_id=comment.id, value=1).score == 1

        with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=15) as api:
            initial = api.put(
                f"{server}/observatory/v2/wikis/softmax/pages/{marker}",
                json={"title": marker, "body": "Initial", "idempotency_key": f"initial-{marker}"},
            )
            initial.raise_for_status()
        page = client.read_wiki_page("softmax", page_slug=marker)
        edited = client.edit_wiki_page(
            "softmax",
            page_slug=marker,
            title=marker,
            body="Updated",
            base_revision_id=page.current_revision_id,
            idempotency_key=f"edit-{marker}",
        )
        assert isinstance(edited, WikiEditPublic)
        assert client.read_wiki_page("softmax", page_slug=marker).current_revision.body == "Updated"
        conflict = client.edit_wiki_page(
            "softmax",
            page_slug=marker,
            title=marker,
            body="Stale",
            base_revision_id=page.current_revision_id,
            idempotency_key=f"stale-{marker}",
        )
        assert isinstance(conflict, WikiEditConflictResponse) and conflict.detail.current_body == "Updated"
        assert {revision.body for revision in client.wiki_history(page.id).entries} == {"Initial", "Updated"}
        assert client.search_wiki("softmax", query=marker).entries[0].page.id == page.id
