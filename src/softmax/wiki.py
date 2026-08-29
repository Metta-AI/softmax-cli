"""Wiki commands for the active Softmax identity."""

from __future__ import annotations

import shlex
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from softmax.auth import DEFAULT_API_SERVER
from softmax.forum_wiki_api import ForumWikiApi, WikiEditConflictResponse

wiki_app = typer.Typer(
    no_args_is_help=True,
    help="Read and edit wikis as the identity in your active token.",
)


@wiki_app.command("read")
def wiki_read(
    wiki_slug: Annotated[str, typer.Argument(help="Wiki slug.")],
    page_slug: Annotated[str, typer.Argument(help="Path-like page slug.")],
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print the full typed response.")] = False,
) -> None:
    """Read the current wiki page."""
    with ForumWikiApi.from_current_token(server) as api:
        page = api.read_wiki_page(wiki_slug, page_slug)
    if json_output:
        print(page.model_dump_json(indent=2))
        return
    typer.echo(page.current_revision.body, nl=False)


@wiki_app.command("edit")
def wiki_edit(
    wiki_slug: Annotated[str, typer.Argument(help="Wiki slug.")],
    page_slug: Annotated[str, typer.Argument(help="Path-like page slug.")],
    file: Annotated[
        Path | None,
        typer.Option(
            "--file", exists=True, dir_okay=False, help="Replacement Markdown file. Opens $EDITOR if omitted."
        ),
    ] = None,
    title: Annotated[str | None, typer.Option(help="Replacement title. Defaults to the current title.")] = None,
    note: Annotated[str | None, typer.Option(help="Revision note.")] = None,
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Edit with compare-and-swap using the revision fetched before editing."""
    with ForumWikiApi.from_current_token(server) as api:
        base = api.read_wiki_page(wiki_slug, page_slug)
        proposed_body = (
            file.read_text() if file is not None else typer.edit(base.current_revision.body, extension=".md")
        )
        if proposed_body is None:
            raise typer.Abort()
        result = api.edit_wiki_page(
            wiki_slug,
            page_slug,
            title=title or base.title,
            body=proposed_body,
            base_revision_id=base.current_revision_id,
            idempotency_key=str(uuid4()),
            note=note,
        )
    if isinstance(result, WikiEditConflictResponse):
        conflict_dir = Path(tempfile.mkdtemp(prefix="softmax-wiki-conflict-"))
        base_path = conflict_dir / "base.md"
        current_path = conflict_dir / "current.md"
        proposed_path = conflict_dir / "proposed.md"
        base_path.write_text(base.current_revision.body)
        current_path.write_text(result.detail.current_body)
        proposed_path.write_text(proposed_body)
        print(f"Wiki edit conflict at revision {result.detail.current_revision_id}.")
        print(shlex.join(["git", "merge-file", str(proposed_path), str(base_path), str(current_path)]))
        retry_command = [
            "softmax",
            "wiki",
            "edit",
            wiki_slug,
            page_slug,
            "--file",
            str(proposed_path),
            "--server",
            server,
        ]
        if title is not None:
            retry_command.extend(["--title", title])
        if note is not None:
            retry_command.extend(["--note", note])
        print(shlex.join(retry_command))
        raise typer.Exit(1)
    if json_output:
        print(result.model_dump_json(indent=2))
        return
    print(f"{result.page.id}\t{result.revision.id}")


@wiki_app.command("history")
def wiki_history(
    wiki_slug: Annotated[str, typer.Argument(help="Wiki slug.")],
    page_slug: Annotated[str, typer.Argument(help="Path-like page slug.")],
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """List the current page's revision history."""
    with ForumWikiApi.from_current_token(server) as api:
        page = api.read_wiki_page(wiki_slug, page_slug)
        history = api.wiki_history(page.id)
    if json_output:
        print(history.model_dump_json(indent=2))
        return
    for revision in history.entries:
        print(f"{revision.id}\t{revision.created_at.isoformat()}\t{revision.author.name}\t{revision.note or ''}")


@wiki_app.command("search")
def wiki_search(
    wiki_slug: Annotated[str, typer.Argument(help="Wiki slug.")],
    query: Annotated[str, typer.Argument(help="Search query.")],
    author_user_id: Annotated[str | None, typer.Option(help="Filter by current user author ID.")] = None,
    author_player_id: Annotated[str | None, typer.Option(help="Filter by current player author ID.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=50)] = 20,
    cursor: Annotated[str | None, typer.Option(help="Cursor from the previous page.")] = None,
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Search current pages in one visible wiki."""
    with ForumWikiApi.from_current_token(server) as api:
        page = api.search_wiki(
            wiki_slug,
            query,
            author_user_id=author_user_id,
            author_player_id=author_player_id,
            limit=limit,
            cursor=cursor,
        )
    if json_output:
        print(page.model_dump_json(indent=2))
        return
    for entry in page.entries:
        print(f"{entry.page.id}\t{entry.rank}\t{entry.page.title}")
    if page.next_cursor is not None:
        print(f"next_cursor\t{page.next_cursor}")
