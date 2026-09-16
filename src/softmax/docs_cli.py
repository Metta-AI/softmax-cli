"""Unauthenticated Markdown retrieval shared by the public CLIs."""

import re
from typing import Annotated

import httpx
import typer

from softmax.agent import user_agent
from softmax.docs import DOCS_AGENT_INDEX_URL, DOCS_AGENT_SKILL_URL, DOCS_URL


def validate_docs_path(path: str) -> None:
    if not re.fullmatch(r"[\w-]+(?:/[\w-]+)*(?:\.md)?", path, flags=re.ASCII):
        raise typer.BadParameter("Use a relative documentation path without URLs, traversal, queries, or fragments.")


def fetch_docs(path: str | None = None, *, skill: bool = False, cli: str = "softmax-cli") -> str:
    if skill and path is not None:
        raise typer.BadParameter("Choose a documentation path or --skill, not both.")
    url = DOCS_AGENT_SKILL_URL if skill else DOCS_AGENT_INDEX_URL
    if path is not None:
        validate_docs_path(path)
        url = f"{DOCS_URL}/{path.removesuffix('.md')}.md"
    response = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": user_agent(cli)})
    response.raise_for_status()
    if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() in {
        "text/html",
        "application/xhtml+xml",
    }:
        typer.echo(f"Error: Expected Markdown, received HTML from {response.url}.", err=True)
        raise typer.Exit(1)
    return response.text


def docs_cmd(
    path: Annotated[str | None, typer.Argument(help="Site-relative page path, with or without .md.")] = None,
    skill: Annotated[bool, typer.Option("--skill", help="Print the agent skill.")] = False,
) -> None:
    """Print the documentation index, a Markdown page, or the agent skill without signing in."""
    typer.echo(fetch_docs(path, skill=skill), nl=False)
