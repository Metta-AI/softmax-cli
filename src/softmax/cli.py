"""softmax CLI — authentication and account tools."""

import sys

import httpx
import typer
from rich._spinners import SPINNERS
from rich.panel import Panel

from softmax import card
from softmax._console import console
from softmax.auth import (
    DEFAULT_API_SERVER,
    ExchangeFailure,
    build_browser_login_url,
    delete_all_tokens,
    fetch_cogames_whoami,
    get_api_server,
    load_current_token,
    load_user_token,
    save_user_token,
    try_exchange_auth_code,
)
from softmax.docs import (
    DOCS_AGENT_INDEX_URL,
    DOCS_AGENT_SKILL_URL,
    DOCS_AUTHENTICATION_URL,
    DOCS_FORUMS_AND_WIKIS_URL,
)
from softmax.docs_cli import docs_cmd
from softmax.forum import forum_app
from softmax.http_errors import AgentFriendlyGroup
from softmax.perform_login import do_interactive_login_for_token
from softmax.players import player_app
from softmax.wiki import wiki_app

app = typer.Typer(
    cls=AgentFriendlyGroup,
    help="Softmax CLI — authentication and account tools",
    epilog=(
        "Run `softmax docs` to read documentation. "
        f"New here? Documentation index: {DOCS_AGENT_INDEX_URL}. Agent skill: {DOCS_AGENT_SKILL_URL}. "
        f"Sign-in and identities: {DOCS_AUTHENTICATION_URL}. The `coworld` CLI drives the player and Coworld workflows."
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.command("docs")(docs_cmd)
app.add_typer(player_app, name="player")
app.add_typer(forum_app, name="forum", epilog=f"Docs: {DOCS_FORUMS_AND_WIKIS_URL}")
app.add_typer(wiki_app, name="wiki", epilog=f"Docs: {DOCS_FORUMS_AND_WIKIS_URL}")


def _build_manual_exchange_command(server: str | None = None) -> str:
    if server:
        return f"softmax exchange-code --server '{server}' '<CODE>'"
    return "softmax exchange-code '<CODE>'"


def _print_non_tty_login_instructions(api_server: str | None = None) -> None:
    resolved = api_server or get_api_server()
    is_custom = resolved != DEFAULT_API_SERVER
    auth_url = build_browser_login_url(resolved)
    console.print("Interactive login requires a TTY.", style="red")
    console.print()
    console.print("Open this URL in any browser to sign in:", style="yellow")
    console.print()
    console.print("    ", auth_url)
    console.print()
    console.print("Copy the auth code from the browser, then run:", style="yellow")
    console.print()
    console.print("    ", _build_manual_exchange_command(resolved if is_custom else None))
    console.print()
    console.print(
        Panel(
            "If you are a coding agent, ask your human to open the URL above and give you "
            "the auth code. Then run the exchange-code command above.",
            title="🤖 Agent Hint",
            border_style="cyan",
        )
    )


def _print_next_steps(api_server: str) -> None:
    """What to do once a token is saved: the same three pointers after login, exchange-code, and set-token."""
    server_option = "" if api_server == DEFAULT_API_SERVER else f" --server {api_server}"
    console.print()
    console.print("Next steps:", style="bold")
    console.print(f"  uv run softmax status{server_option}    # confirm the identity behind this token")
    console.print(f"  uv run coworld leagues{server_option}   # pick a league; each one prints its participation guide")
    console.print(f"  Documentation index: {DOCS_AGENT_INDEX_URL}")
    console.print(f"  Agent skill: {DOCS_AGENT_SKILL_URL}")


@app.command(name="login")
def login_cmd(
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Skip opening browser automatically.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Re-authenticate even if already logged in",
    ),
    server: str | None = typer.Option(
        None,
        "--server",
        "-s",
        metavar="URL",
        help="API server URL.",
    ),
) -> None:
    """Sign in to Softmax."""
    from urllib.parse import urlparse  # noqa: PLC0415

    api_server = server or get_api_server()
    user_token = None if force else load_user_token(server=api_server)
    if user_token is not None:
        try:
            whoami = fetch_cogames_whoami(api_server=api_server, token=user_token)
            if whoami.subject_type == "anonymous":
                console.print("Saved token is no longer valid. Re-authenticating...", style="yellow")
                user_token = None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                console.print("Saved token is no longer valid. Re-authenticating...", style="yellow")
                user_token = None
            else:
                console.print(f"Could not verify token (HTTP {exc.response.status_code}), proceeding.", style="yellow")
        except httpx.HTTPError:
            console.print("Could not reach server to verify token. Proceeding with saved token.", style="yellow")

    if user_token is not None:
        console.print(f"Already authenticated with {urlparse(api_server).hostname}", style="green")
        return

    if not sys.stdin.isatty():
        _print_non_tty_login_instructions(api_server)
        raise typer.Exit(1)

    try:
        do_interactive_login_for_token(
            api_server=api_server,
            agent_hint=None,
            open_browser=not no_browser,
        )
    except Exception as e:
        console.print()
        console.print(f"Error: {e}", style="red", highlight=False)
        console.print()
        console.print("Authentication failed.", style="red")
        raise typer.Exit(1) from e

    console.print("Authentication successful.", style="green")
    _print_next_steps(api_server)


@app.command(name="logout")
def logout_cmd(
    server: str | None = typer.Option(
        None,
        "--server",
        "-s",
        metavar="URL",
        help="API server URL.",
    ),
) -> None:
    """Remove saved authentication token."""
    api_server = server or get_api_server()
    if delete_all_tokens(server=api_server):
        console.print("Logged out.", style="green")
    else:
        console.print("No token found — already logged out.", style="yellow")


@app.command(name="get-login-url")
def get_login_url_cmd(
    server: str | None = typer.Option(
        None,
        "--server",
        "-s",
        metavar="URL",
        help="API server URL.",
    ),
) -> None:
    """Print a browser sign-in URL for manual login."""
    print(build_browser_login_url(server or get_api_server()))


@app.command(name="status")
def status_cmd(
    server: str | None = typer.Option(
        None,
        "--server",
        "-s",
        metavar="URL",
        help="API server URL.",
    ),
    elevated: bool = typer.Option(
        False,
        "--elevated",
        help=(
            "Ask the server to honor this token's Softmax-team privileges for this "
            "request. Team access is opt-in per request (never automatic) -- "
            "without this flag a team member's own token reports as a non-member, "
            "the same external-by-default view the web app gives employees unless "
            "they flip the same toggle there."
        ),
    ),
) -> None:
    """Check authentication status via /whoami."""
    from softmax.auth import get_active_player_id, load_player_session  # noqa: PLC0415

    api_server = server or get_api_server()
    token = load_current_token(server=api_server)
    if not token:
        console.print("[red]Not authenticated.[/red] Run [cyan]softmax login[/cyan] first.")
        raise typer.Exit(1)

    session = fetch_cogames_whoami(api_server=api_server, token=token, elevated=elevated)
    if session.subject_type == "anonymous":
        player_token = load_player_session(server=api_server)
        if player_token and player_token == token:
            player_id = get_active_player_id(server=api_server)
            console.print(
                f"[red]Active player session expired[/red] ({player_id})."
                " Run [cyan]softmax player use[/cyan] to refresh"
                " or [cyan]softmax player unset[/cyan] to revert to your user credential."
            )
            raise typer.Exit(1)
        console.print("[red]Token is invalid or expired.[/red] Run [cyan]softmax login[/cyan] to re-authenticate.")
        raise typer.Exit(1)
    console.print("[green]Authenticated[/green]")
    console.print(f"user_email: {session.user_email}")
    console.print(f"subject_type: {session.subject_type}")
    console.print(f"subject_id: {session.subject_id or '-'}")
    console.print(f"owner_user_id: {session.owner_user_id or '-'}")
    # Always shown, not just with --elevated: this is the one line that tells you
    # whether elevation did anything. Without --elevated it reads false even for a
    # real team member (the server treats every request as external unless asked
    # otherwise); a plain run and an elevated run must never look identical here.
    console.print(f"is_softmax_team_member: {session.is_softmax_team_member}")
    console.print(f"is_softmax_admin: {session.is_softmax_admin}")


@app.command(name="get-token")
def get_token_cmd(
    server: str | None = typer.Option(
        None,
        "--server",
        "-s",
        metavar="URL",
        help="API server URL.",
    ),
) -> None:
    """Print the saved token to stdout (for scripting)."""
    api_server = server or get_api_server()
    token = load_current_token(server=api_server)
    if not token:
        console.print("[red]No token found.[/red] Run [cyan]softmax login[/cyan] first.", style="bold")
        raise typer.Exit(1)
    print(token)


@app.command(name="set-token")
def set_token_cmd(
    token: str = typer.Argument(help="Bearer token to save"),
    server: str | None = typer.Option(
        None,
        "--server",
        "-s",
        metavar="URL",
        help="API server URL.",
    ),
) -> None:
    """Manually set a token (for CI or headless environments)."""
    api_server = server or get_api_server()
    save_user_token(server=api_server, token=token)
    print(f"\nToken saved for {api_server}")
    _print_next_steps(api_server)


@app.command(name="exchange-code")
def exchange_code_cmd(
    code: str = typer.Argument(help="One-time auth code from browser login"),
    server: str | None = typer.Option(
        None,
        "--server",
        "-s",
        metavar="URL",
        help="API server URL.",
    ),
) -> None:
    """Exchange a one-time auth code for a credential."""
    api_server = server or get_api_server()
    result = try_exchange_auth_code(api_server=api_server, code=code)
    if isinstance(result, ExchangeFailure):
        console.print(result.message, style="red", highlight=False)
        raise typer.Exit(1)
    save_user_token(server=api_server, token=result.token)
    print(f"\nToken saved for {api_server}")
    _print_next_steps(api_server)


# `softmax card` loader: the card's own 8-cell stat bar as a softmax
# distribution whose peak sweeps while the standings load. Registered into
# rich's spinner table so console.status can animate it.
_WAVE = "▁▂▄▆█▆▄▂"
SPINNERS["softmax"] = {
    "interval": 90,
    "frames": [_WAVE[-i:] + _WAVE[:-i] for i in range(len(_WAVE))],
}


@app.command(name="card")
def card_cmd(
    name: str | None = typer.Argument(None, help="Wordmark override (A-Z and space)."),
    demo: bool = typer.Option(False, "--demo", help="Render the sample card instead of live standings."),
) -> None:
    """Render your player card: live league standings as a terminal collectible."""
    if demo:
        cards = [card.DEMO_CARD]
    else:
        api_server = get_api_server()
        token = load_user_token(server=api_server)
        if not token:
            console.print(
                "[red]Not authenticated.[/red] Run [cyan]softmax login[/cyan] first,"
                " or try [cyan]softmax card --demo[/cyan]."
            )
            raise typer.Exit(1)
        if console.is_terminal:
            # The loader line erases itself once the card is ready; piped
            # output never sees it.
            with console.status("[dim]dealing your card[/dim]", spinner="softmax", spinner_style="dim") as status:
                cards = card.fetch_player_cards(
                    api_server, token, on_stage=lambda line: status.update(f"[dim]{line}[/dim]")
                )
        else:
            cards = card.fetch_player_cards(api_server, token)
    if name:
        mark = name.upper()
        unsupported = sorted(set(mark) - card.SUPPORTED_NAME_CHARS)
        if unsupported:
            supported = " ".join(sorted(card.SUPPORTED_NAME_CHARS))
            raise typer.BadParameter(f"the pixel font has no {' '.join(unsupported)} (available: {supported})")
        cards = [c.model_copy(update={"name": mark}) for c in cards]
    print("\n\n".join(card.render(c) for c in cards))
    if demo:
        console.print("  [dim]demo standings[/dim]")
