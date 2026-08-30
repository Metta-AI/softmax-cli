from __future__ import annotations

import json

import httpx

from softmax.forum_wiki_api import ForumWikiApi, WikiEditConflictResponse

POST = {
    "id": "post_1",
    "title": "Hello",
    "author": {"type": "user", "user_id": "usr_1", "name": "Ada"},
    "content_format": "markdown",
    "body": "Body",
    "media": [],
    "created_at": "2026-08-29T00:00:00Z",
    "score": 1,
    "vote_count": 1,
}
COMMENT = {
    "id": "cmt_1",
    "parent_id": None,
    "author": {"type": "player", "player_id": "ply_1", "name": "Bot", "avatar_url": None},
    "body": "Reply",
    "created_at": "2026-08-29T00:01:00Z",
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


def test_forum_api_uses_exact_paths_bearer_and_scriptable_models() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/observatory/v2/forums/global/posts":
            return httpx.Response(200, json={"entries": [POST], "next_cursor": None})
        if path == "/observatory/v2/posts/post_1.md":
            return httpx.Response(200, text="# Hello\n")
        if path == "/observatory/v2/posts":
            return httpx.Response(201, json=POST)
        if path == "/observatory/v2/posts/post_1/comments":
            return httpx.Response(201, json=COMMENT)
        if path == "/observatory/v2/posts/post_1/vote":
            return httpx.Response(200, json={"value": 1, "score": 2, "vote_count": 2})
        if path == "/observatory/v2/posts/post_1/comments/cmt_1/vote":
            return httpx.Response(200, json={"value": -1, "score": -1, "vote_count": None})
        if path == "/observatory/v2/forums/global/search":
            return httpx.Response(
                200,
                json={
                    "entries": [{"post": POST, "rank": 0.5}],
                    "next_cursor": None,
                    "result_quality": "exact_within_forum",
                    "candidate_limit": None,
                    "older_matches_may_be_omitted": False,
                },
            )
        if path == "/observatory/v2/forums/search":
            return httpx.Response(
                200,
                json={
                    "entries": [{"post": POST, "rank": 0.5}],
                    "next_cursor": None,
                    "result_quality": "newest_5000_candidates",
                    "candidate_limit": 5000,
                    "older_matches_may_be_omitted": True,
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    with ForumWikiApi(
        server="https://softmax.test",
        token="identity-token",
        transport=httpx.MockTransport(handler),
    ) as api:
        assert api.list_forum("global", sort="new", limit=10).entries[0].id == "post_1"
        assert api.read_post("post_1") == "# Hello\n"
        assert api.create_post(title="Hello", body="Body", idempotency_key="post-key").title == "Hello"
        assert api.create_comment("post_1", body="Reply", idempotency_key="comment-key").id == "cmt_1"
        assert api.vote("post_1", value=1).score == 2
        assert api.vote("post_1", comment_id="cmt_1", value=-1).score == -1
        assert api.search_forum("query", forum_slug="global").entries[0].post.id == "post_1"
        assert api.search_forum("query").result_quality == "newest_5000_candidates"

    assert [request.url.path for request in requests] == [
        "/observatory/v2/forums/global/posts",
        "/observatory/v2/posts/post_1.md",
        "/observatory/v2/posts",
        "/observatory/v2/posts/post_1/comments",
        "/observatory/v2/posts/post_1/vote",
        "/observatory/v2/posts/post_1/comments/cmt_1/vote",
        "/observatory/v2/forums/global/search",
        "/observatory/v2/forums/search",
    ]
    assert all(request.headers["Authorization"] == "Bearer identity-token" for request in requests)
    assert dict(requests[0].url.params) == {"sort": "new", "limit": "10"}
    assert requests[-1].url.params["q"] == "query"


def test_wiki_api_uses_exact_paths_and_parses_typed_conflict() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/observatory/v2/wikis/global/pages/guide/start" and request.method == "GET":
            return httpx.Response(200, json=PAGE)
        if path == "/observatory/v2/wikis/global/pages/guide/start" and request.method == "PUT":
            return httpx.Response(
                409,
                json={
                    "detail": {
                        "type": "wiki_edit_conflict",
                        "current_revision_id": "wrv_2",
                        "current_body": "Current",
                    }
                },
            )
        if path == "/observatory/v2/wiki-pages/wpg_1/revisions":
            return httpx.Response(200, json={"entries": [PAGE["current_revision"]]})
        if path == "/observatory/v2/wikis/global/search":
            summary = {key: value for key, value in PAGE.items() if key != "current_revision"}
            return httpx.Response(
                200,
                json={
                    "entries": [
                        {
                            "page": summary,
                            "current_author": {"type": "user", "user_id": "usr_1", "name": "Ada"},
                            "rank": 0.75,
                        }
                    ],
                    "next_cursor": None,
                    "result_quality": "exact_within_wiki",
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    with ForumWikiApi(
        server="https://softmax.test",
        token="identity-token",
        transport=httpx.MockTransport(handler),
    ) as api:
        assert api.read_wiki_page("global", "guide/start").current_revision.body == "Base"
        conflict = api.edit_wiki_page(
            "global",
            "guide/start",
            title="Start",
            body="Proposed",
            base_revision_id="wrv_1",
            idempotency_key="edit-key",
        )
        assert isinstance(conflict, WikiEditConflictResponse)
        assert conflict.detail.current_body == "Current"
        assert api.wiki_history("wpg_1").entries[0].id == "wrv_1"
        assert api.search_wiki("global", "query").entries[0].page.id == "wpg_1"

    assert [request.url.path for request in requests] == [
        "/observatory/v2/wikis/global/pages/guide/start",
        "/observatory/v2/wikis/global/pages/guide/start",
        "/observatory/v2/wiki-pages/wpg_1/revisions",
        "/observatory/v2/wikis/global/search",
    ]
    assert all(request.headers["Authorization"] == "Bearer identity-token" for request in requests)


def test_mutations_retain_idempotency_keys_across_retries() -> None:
    bodies: dict[str, list[dict[str, object]]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        path_bodies = bodies.setdefault(path, [])
        path_bodies.append(json.loads(request.content))
        if len(path_bodies) == 1:
            return httpx.Response(503, json={"detail": "retry"})
        if path == "/observatory/v2/posts":
            return httpx.Response(201, json=POST)
        if path == "/observatory/v2/posts/post_1/comments":
            return httpx.Response(201, json=COMMENT)
        if path == "/observatory/v2/wikis/global/pages/guide/start":
            summary = {key: value for key, value in PAGE.items() if key != "current_revision"}
            return httpx.Response(200, json={"page": summary, "revision": PAGE["current_revision"]})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    with ForumWikiApi(
        server="https://softmax.test",
        token="identity-token",
        transport=httpx.MockTransport(handler),
    ) as api:
        api.create_post(title="Hello", body="Body", idempotency_key="stable-key")
        api.create_comment("post_1", body="Reply", idempotency_key="comment-key")
        api.edit_wiki_page(
            "global",
            "guide/start",
            title="Start",
            body="Proposed",
            base_revision_id="wrv_1",
            idempotency_key="edit-key",
        )

    assert [body["idempotency_key"] for body in bodies["/observatory/v2/posts"]] == ["stable-key", "stable-key"]
    assert [body["idempotency_key"] for body in bodies["/observatory/v2/posts/post_1/comments"]] == [
        "comment-key",
        "comment-key",
    ]
    assert [body["idempotency_key"] for body in bodies["/observatory/v2/wikis/global/pages/guide/start"]] == [
        "edit-key",
        "edit-key",
    ]
