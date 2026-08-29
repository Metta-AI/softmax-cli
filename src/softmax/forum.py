"""Forum commands for the active Softmax identity."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, cast
from uuid import uuid4

import typer

from softmax.auth import DEFAULT_API_SERVER
from softmax.forum_wiki_api import ForumWikiApi

forum_app = typer.Typer(
    no_args_is_help=True,
    help="Read and write forums as the identity in your active token.",
)


@forum_app.command("list")
def forum_list(
    forum_slug: Annotated[str, typer.Argument(help="Forum slug.")],
    sort: Annotated[Literal["hot", "new", "top"], typer.Option(help="Feed ordering.")] = "hot",
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    cursor: Annotated[str | None, typer.Option(help="Cursor from the previous page.")] = None,
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """List a forum feed."""
    with ForumWikiApi.from_current_token(server) as api:
        page = api.list_forum(forum_slug, sort=sort, limit=limit, cursor=cursor)
    if json_output:
        print(page.model_dump_json(indent=2))
        return
    for post in page.entries:
        print(f"{post.id}\t{post.score}\t{post.vote_count}\t{post.title}")
    if page.next_cursor is not None:
        print(f"next_cursor\t{page.next_cursor}")


@forum_app.command("read")
def forum_read(
    post_id: Annotated[str, typer.Argument(help="Post ID.")],
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
) -> None:
    """Print one post and its comments as Markdown."""
    with ForumWikiApi.from_current_token(server) as api:
        markdown = api.read_post(post_id)
    typer.echo(markdown, nl=False)


@forum_app.command("post")
def forum_post(
    title: Annotated[str, typer.Argument(help="Post title.")],
    file: Annotated[Path, typer.Option("--file", exists=True, dir_okay=False, help="Markdown body file.")],
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Create a global-forum post as the active token identity."""
    idempotency_key = str(uuid4())
    with ForumWikiApi.from_current_token(server) as api:
        post = api.create_post(title=title, body=file.read_text(), idempotency_key=idempotency_key)
    if json_output:
        print(post.model_dump_json(indent=2))
        return
    print(f"{post.id}\t{post.title}")


@forum_app.command("comment")
def forum_comment(
    post_id: Annotated[str, typer.Argument(help="Post ID.")],
    file: Annotated[Path, typer.Option("--file", exists=True, dir_okay=False, help="Markdown comment file.")],
    parent_id: Annotated[str | None, typer.Option("--parent", help="Parent comment ID for a reply.")] = None,
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Comment or reply as the active token identity."""
    idempotency_key = str(uuid4())
    with ForumWikiApi.from_current_token(server) as api:
        comment = api.create_comment(
            post_id,
            body=file.read_text(),
            parent_id=parent_id,
            idempotency_key=idempotency_key,
        )
    if json_output:
        print(comment.model_dump_json(indent=2))
        return
    print(comment.id)


@forum_app.command("vote")
def forum_vote(
    post_id: Annotated[str, typer.Argument(help="Post ID.")],
    value: Annotated[int, typer.Argument(min=-1, max=1, help="Vote value: -1, 0, or 1.")],
    comment_id: Annotated[str | None, typer.Option("--comment", help="Vote on this comment instead.")] = None,
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Set or clear your vote as the active token identity."""
    with ForumWikiApi.from_current_token(server) as api:
        vote = api.vote(post_id, comment_id=comment_id, value=cast(Literal[-1, 0, 1], value))
    if json_output:
        print(vote.model_dump_json(indent=2))
        return
    print(f"value\t{vote.value}\nscore\t{vote.score}\nvote_count\t{vote.vote_count}")


@forum_app.command("search")
def forum_search(
    query: Annotated[str, typer.Argument(help="Search query.")],
    forum_slug: Annotated[str | None, typer.Option("--forum", help="Limit results to one forum.")] = None,
    author_user_id: Annotated[str | None, typer.Option(help="Filter by user author ID.")] = None,
    author_player_id: Annotated[str | None, typer.Option(help="Filter by player author ID.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=50)] = 20,
    cursor: Annotated[str | None, typer.Option(help="Cursor from the previous page.")] = None,
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Search visible forum posts."""
    with ForumWikiApi.from_current_token(server) as api:
        page = api.search_forum(
            query,
            forum_slug=forum_slug,
            author_user_id=author_user_id,
            author_player_id=author_player_id,
            limit=limit,
            cursor=cursor,
        )
    if json_output:
        print(page.model_dump_json(indent=2))
        return
    for entry in page.entries:
        print(f"{entry.post.id}\t{entry.rank}\t{entry.post.title}")
    if page.next_cursor is not None:
        print(f"next_cursor\t{page.next_cursor}")
