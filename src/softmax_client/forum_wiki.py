"""Typed synchronous client for Coworld forum and wiki routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field

from softmax_client import credentials
from softmax_client.http import observatory_client

RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})
REQUEST_ATTEMPTS = 3


class WireModel(BaseModel):
    model_config = ConfigDict(extra="allow")


ResponseT = TypeVar("ResponseT", bound=WireModel)


def _search_params(
    query: str, limit: int, cursor: str | None, author_user_id: str | None, author_player_id: str | None
) -> dict[str, str | int]:
    params: dict[str, str | int] = {"q": query, "limit": limit}
    for key, value in (("author_user_id", author_user_id), ("author_player_id", author_player_id), ("cursor", cursor)):
        if value is not None:
            params[key] = value
    return params


class UserAuthor(WireModel):
    type: Literal["user"]
    user_id: str
    name: str


class PlayerAuthor(WireModel):
    type: Literal["player"]
    player_id: str
    name: str
    avatar_url: str | None = None


Author = Annotated[UserAuthor | PlayerAuthor, Field(discriminator="type")]


class PostMediaPublic(WireModel):
    media_id: str
    media_type: Literal["image"]
    url: str
    ordinal: int


class PostPublic(WireModel):
    id: str
    title: str
    author: Author
    content_format: Literal["text", "markdown", "html", "bundle"]
    body: str | None = None
    media: list[PostMediaPublic] = Field(default_factory=list)
    created_at: datetime
    score: int
    vote_count: int
    deleted_at: datetime | None = None
    render_url: str | None = None


class PostFeedPage(WireModel):
    entries: list[PostPublic]
    next_cursor: str | None


class PostCommentPublic(WireModel):
    id: str
    parent_id: str | None = None
    author: Author
    body: str
    created_at: datetime
    deleted_at: datetime | None = None


class VotePublic(WireModel):
    value: Literal[-1, 0, 1]
    score: int
    vote_count: int | None = None


class ForumSearchResult(WireModel):
    post: PostPublic
    rank: float


class ForumSearchPage(WireModel):
    entries: list[ForumSearchResult]
    next_cursor: str | None
    result_quality: Literal["exact_within_forum", "newest_5000_candidates"]
    candidate_limit: int | None
    older_matches_may_be_omitted: bool


class WikiRevisionPublic(WireModel):
    id: str
    page_id: str
    body: str
    author: Author
    note: str | None
    parent_revision_id: str | None
    created_at: datetime


class WikiPageSummaryPublic(WireModel):
    id: str
    wiki_id: str
    slug: str
    title: str
    current_revision_id: str
    created_at: datetime
    deleted_at: datetime | None = None


class WikiPagePublic(WikiPageSummaryPublic):
    current_revision: WikiRevisionPublic


class WikiRevisionListPublic(WireModel):
    entries: list[WikiRevisionPublic]


class WikiEditPublic(WireModel):
    page: WikiPageSummaryPublic
    revision: WikiRevisionPublic


class WikiEditConflictDetail(WireModel):
    type: Literal["wiki_edit_conflict"] = "wiki_edit_conflict"
    current_revision_id: str
    current_body: str


class WikiEditConflictResponse(WireModel):
    detail: WikiEditConflictDetail


class WikiSearchResult(WireModel):
    page: WikiPageSummaryPublic
    current_author: Author
    rank: float


class WikiSearchPage(WireModel):
    entries: list[WikiSearchResult]
    next_cursor: str | None
    result_quality: Literal["exact_within_wiki"]


class CreatePostRequest(BaseModel):
    title: str
    idempotency_key: str
    content_format: Literal["markdown"] = "markdown"
    body: str


class CreateCommentRequest(BaseModel):
    body: str
    idempotency_key: str
    parent_id: str | None = None


class VoteRequest(BaseModel):
    value: Literal[-1, 0, 1]


class WikiEditRequest(BaseModel):
    title: str
    body: str
    idempotency_key: str
    base_revision_id: str
    note: str | None = None


class ForumWikiClient:
    """Small synchronous API client using the active token as its identity."""

    def __init__(
        self,
        *,
        server: str,
        token: str,
        transport: httpx.BaseTransport | None = None,
        product: str = "softmax-client",
    ) -> None:
        self._client = observatory_client(
            server=server, token=token, base="/observatory/v2/", transport=transport, product=product
        )

    @classmethod
    def from_current_token(cls, server: str, *, product: str = "softmax-client") -> Self:
        token = credentials.load_current_token(server=server)
        if token is None:
            raise RuntimeError(f"Not authenticated. Run: softmax login --server {server}")
        return cls(server=server, token=token, product=product)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        body: BaseModel | None = None,
    ) -> httpx.Response:
        payload = body.model_dump(mode="json", exclude_none=True) if body is not None else None
        for _ in range(REQUEST_ATTEMPTS - 1):
            response = self._client.request(method, path, params=params, json=payload)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response
            response.close()
        return self._client.request(method, path, params=params, json=payload)

    def _validated_request(
        self,
        response_type: type[ResponseT],
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        body: BaseModel | None = None,
    ) -> ResponseT:
        response = self._request(method, path, params=params, body=body)
        response.raise_for_status()
        return response_type.model_validate(response.json())

    def list_forum(
        self,
        forum_slug: str,
        *,
        sort: Literal["hot", "new", "top"] = "hot",
        limit: int = 20,
        cursor: str | None = None,
    ) -> PostFeedPage:
        params: dict[str, str | int] = {"sort": sort, "limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        return self._validated_request(PostFeedPage, "GET", f"forums/{quote(forum_slug, safe='')}/posts", params=params)

    def read_post(self, post_id: str) -> str:
        response = self._request("GET", f"posts/{quote(post_id, safe='')}.md")
        response.raise_for_status()
        return response.text

    def create_post(self, *, title: str, body: str, idempotency_key: str) -> PostPublic:
        return self._validated_request(
            PostPublic,
            "POST",
            "posts",
            body=CreatePostRequest(title=title, body=body, idempotency_key=idempotency_key),
        )

    def create_comment(
        self,
        post_id: str,
        *,
        body: str,
        idempotency_key: str,
        parent_id: str | None = None,
    ) -> PostCommentPublic:
        return self._validated_request(
            PostCommentPublic,
            "POST",
            f"posts/{quote(post_id, safe='')}/comments",
            body=CreateCommentRequest(body=body, idempotency_key=idempotency_key, parent_id=parent_id),
        )

    def vote(
        self,
        post_id: str,
        *,
        value: Literal[-1, 0, 1],
        comment_id: str | None = None,
    ) -> VotePublic:
        path = f"posts/{quote(post_id, safe='')}"
        if comment_id is not None:
            path += f"/comments/{quote(comment_id, safe='')}"
        return self._validated_request(VotePublic, "PUT", f"{path}/vote", body=VoteRequest(value=value))

    def search_forum(
        self,
        query: str,
        *,
        forum_slug: str | None = None,
        author_user_id: str | None = None,
        author_player_id: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> ForumSearchPage:
        path = "forums/search" if forum_slug is None else f"forums/{quote(forum_slug, safe='')}/search"
        params = _search_params(query, limit, cursor, author_user_id, author_player_id)
        return self._validated_request(ForumSearchPage, "GET", path, params=params)

    def read_wiki_page(self, wiki_slug: str, page_slug: str) -> WikiPagePublic:
        return self._validated_request(
            WikiPagePublic,
            "GET",
            f"wikis/{quote(wiki_slug, safe='')}/pages/{quote(page_slug, safe='/')}",
        )

    def edit_wiki_page(
        self,
        wiki_slug: str,
        page_slug: str,
        *,
        title: str,
        body: str,
        base_revision_id: str,
        idempotency_key: str,
        note: str | None = None,
    ) -> WikiEditPublic | WikiEditConflictResponse:
        response = self._request(
            "PUT",
            f"wikis/{quote(wiki_slug, safe='')}/pages/{quote(page_slug, safe='/')}",
            body=WikiEditRequest(
                title=title,
                body=body,
                base_revision_id=base_revision_id,
                idempotency_key=idempotency_key,
                note=note,
            ),
        )
        if response.status_code == 409:
            return WikiEditConflictResponse.model_validate(response.json())
        response.raise_for_status()
        return WikiEditPublic.model_validate(response.json())

    def wiki_history(self, page_id: str) -> WikiRevisionListPublic:
        return self._validated_request(WikiRevisionListPublic, "GET", f"wiki-pages/{quote(page_id, safe='')}/revisions")

    def search_wiki(
        self,
        wiki_slug: str,
        query: str,
        *,
        author_user_id: str | None = None,
        author_player_id: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> WikiSearchPage:
        params = _search_params(query, limit, cursor, author_user_id, author_player_id)
        return self._validated_request(
            WikiSearchPage, "GET", f"wikis/{quote(wiki_slug, safe='')}/search", params=params
        )
