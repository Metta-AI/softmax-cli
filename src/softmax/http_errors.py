"""Render Observatory HTTP failures as actionable terminal errors.

A failed request used to escape the CLIs as a raw traceback whose only link was MDN's page for
the status code. The reader (usually a coding agent) needs the status, the route, the server's
detail, the request id to quote in a bug report, and the one thing to do next. `AgentFriendlyGroup`
installs that rendering at the command boundary of a Typer app.
"""

from __future__ import annotations

import contextlib
import json
import sys
from typing import Any

import click
import httpx
import typer
from typer.core import TyperGroup

from softmax.agent import detect_coding_agent
from softmax.docs import DOCS_AUTHENTICATION_URL, DOCS_ERROR_HANDLING_URL, DOCS_RATE_LIMITS_URL

REQUEST_ID_HEADER = "X-Request-Id"

# typer 0.27+ vendors its own click fork: the usage errors its parser raises are
# `typer._click.exceptions.UsageError`, unrelated to `click.UsageError`, and its main loop
# catches `typer.Exit` rather than click's Exit. Older typer runs on the real click. Catch
# both usage-error families so the group behaves identically under either.
try:
    from typer._click.exceptions import UsageError as _VendoredUsageError
except ImportError:  # typer < 0.27 runs on the real click
    USAGE_ERRORS: tuple[type[Exception], ...] = (click.UsageError,)
else:
    USAGE_ERRORS = (click.UsageError, _VendoredUsageError)


def _detail_lines(response: httpx.Response) -> tuple[list[str], str | None]:
    """The server's error detail as printable lines, plus its documentation_url when it sent one."""
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        text = response.text.strip()
        return ([f"Detail: {text[:400]}"] if text else [], None)
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        return [f"Detail: {detail}"], None
    if isinstance(detail, dict):
        lines = []
        if isinstance(detail.get("type"), str):
            lines.append(f"Type: {detail['type']}")
        if isinstance(detail.get("message"), str):
            lines.append(f"Detail: {detail['message']}")
        documentation_url = detail.get("documentation_url")
        return lines, documentation_url if isinstance(documentation_url, str) else None
    if detail is not None:
        return [f"Detail: {json.dumps(detail)[:400]}"], None
    return [], None


def _next_step(status_code: int, response: httpx.Response) -> str:
    if status_code == 401:
        return "Next: run `uv run softmax status`; if the token is missing or expired, run `uv run softmax login`."
    if status_code == 403:
        return (
            "Next: this identity is not allowed here. Check `uv run softmax status` and the active player "
            "(`uv run softmax player list`)."
        )
    if status_code == 404:
        return (
            "Next: check the id and the server URL. `uv run coworld list` and `uv run coworld leagues` show valid ids."
        )
    if status_code == 409:
        return "Next: re-read the current state the response describes, then retry with that as the base."
    if status_code == 429:
        retry_after = response.headers.get("Retry-After")
        wait = f"at least {retry_after}s" if retry_after else "the Retry-After delay"
        return f"Next: wait {wait}, reduce concurrency, then retry."
    if status_code in (400, 422):
        return "Next: fix the request; the detail names the invalid field. Do not retry unchanged input."
    if status_code >= 500:
        return "Next: retry with backoff. If it persists, report the request id below."
    return "Next: read the detail above."


def render_http_status_error(exc: httpx.HTTPStatusError) -> str:
    """One terminal-ready message: what failed, what the server said, what to do, where to read."""
    response = exc.response
    request = exc.request
    status = response.status_code
    detail_lines, documentation_url = _detail_lines(response)
    if str(exc).startswith(("Client error '", "Server error '")):
        # httpx's own message: say what failed ourselves, then the server's detail.
        lines = [f"Request failed: {request.method} {request.url.path} returned HTTP {status}.", *detail_lines]
    else:
        # A client crafted the message (status, path, hint); it already says what failed.
        lines = [str(exc)]
    lines.append(_next_step(status, response))
    request_id = response.headers.get(REQUEST_ID_HEADER)
    if request_id:
        lines.append(f"Request id: {request_id}")
    if documentation_url is None:
        if status in (401, 403):
            documentation_url = DOCS_AUTHENTICATION_URL
        elif status == 429:
            documentation_url = DOCS_RATE_LIMITS_URL
        else:
            documentation_url = DOCS_ERROR_HANDLING_URL
    lines.append(f"Docs: {documentation_url}")
    return "\n".join(lines)


class AgentFriendlyGroup(TyperGroup):
    """Typer group whose commands report failures in a form an agent can act on.

    - `httpx.HTTPStatusError` becomes a rendered error, plain text on stderr and exit 1, instead
      of a traceback. It is the typed failure of a request that reached the server and was
      refused, and the response carries everything the message needs. Every other exception
      still propagates with its traceback.
    - A usage error (unknown flag, missing argument) under a coding agent prints the command's
      full help before the usual one-line hint, the way the GitHub CLI does, so the agent can
      correct the call without a second round trip.
    """

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: Any,
    ) -> click.Context:
        # Root-level parsing (`softmax --bogus`) raises before invoke() runs.
        try:
            return super().make_context(info_name, args, parent, **extra)
        except USAGE_ERRORS as exc:
            _echo_help_for_agent(exc.ctx)
            raise

    def invoke(self, ctx: click.Context) -> object:
        try:
            return super().invoke(ctx)
        except httpx.HTTPStatusError as exc:
            # Plain echo, not ClickException: Typer boxes those with Rich and wraps at the
            # terminal width, which splits URLs and hints that an agent needs verbatim.
            click.echo(f"Error: {render_http_status_error(exc)}", err=True)
            raise typer.Exit(1) from exc
        except USAGE_ERRORS as exc:
            _echo_help_for_agent(exc.ctx or ctx)
            raise


def _echo_help_for_agent(ctx: click.Context | None) -> None:
    if ctx is None or detect_coding_agent() is None:
        return
    # Typer's Rich formatter prints the help while get_help() runs instead of returning it,
    # and it prints to stdout. Usage errors belong on stderr, so redirect for the render.
    with contextlib.redirect_stdout(sys.stderr):
        rendered = ctx.get_help()
        if rendered:
            click.echo(rendered)
    click.echo(err=True)
