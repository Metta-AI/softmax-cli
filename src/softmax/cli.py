"""softmax CLI — authentication and account tools."""

import sys

import httpx
import typer
from rich.panel import Panel

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
from softmax.perform_login import do_interactive_login_for_token

app = typer.Typer(
    help="Softmax CLI — authentication and account tools",
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
    rich_markup_mode="rich",
)


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
) -> None:
    """Check authentication status via /whoami."""
    api_server = server or get_api_server()
    token = load_current_token(server=api_server)
    if not token:
        console.print("[red]Not authenticated.[/red] Run [cyan]softmax login[/cyan] first.")
        raise typer.Exit(1)

    session = fetch_cogames_whoami(api_server=api_server, token=token)
    if session.subject_type == "anonymous":
        console.print("[red]Token is invalid or expired.[/red] Run [cyan]softmax login[/cyan] to re-authenticate.")
        raise typer.Exit(1)
    console.print("[green]Authenticated[/green]")
    console.print(f"user_email: {session.user_email}")
    console.print(f"subject_type: {session.subject_type}")
    console.print(f"subject_id: {session.subject_id or '-'}")
    console.print(f"owner_user_id: {session.owner_user_id or '-'}")


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
