"""softmax CLI — authentication and account tools."""

import importlib
import importlib.util
import sys

import typer
from rich.panel import Panel

from softmax._console import console
from softmax.auth import (
    DEFAULT_COGAMES_SERVER,
    build_browser_login_url,
    delete_cogames_tokens,
    fetch_cogames_whoami,
    load_cogames_user_token,
    load_current_cogames_token,
    save_cogames_active_token,
    save_cogames_user_token,
)
from softmax.perform_login import do_interactive_login_for_token
from softmax.token_storage import TokenKind

app = typer.Typer(
    help="Softmax CLI — authentication and account tools",
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _register_optional_apps() -> None:
    if importlib.util.find_spec("cogames") is None:
        return
    if importlib.util.find_spec("cogames.softmax_cli") is None:
        return

    cogames_cli = importlib.import_module("cogames.softmax_cli")
    app.add_typer(cogames_cli.app, name="cogames", rich_help_panel="Local Games")


def _build_manual_set_token_command(*, login_server: str) -> str:
    command = "softmax set-token '<TOKEN>'"
    if login_server != DEFAULT_COGAMES_SERVER:
        command += f" --login-server '{login_server}'"
    return command


def _print_non_tty_login_instructions(*, login_server: str) -> None:
    auth_url = build_browser_login_url(login_server)
    console.print("Interactive login requires a TTY.", style="red")
    console.print()
    console.print("Open this URL in any browser to sign in:", style="yellow")
    console.print()
    console.print("    ", auth_url)
    console.print()
    console.print("Copy the auth token from the browser, then run:", style="yellow")
    console.print()
    console.print("    ", _build_manual_set_token_command(login_server=login_server))
    console.print()
    console.print(
        Panel(
            "If you are a coding agent, ask your human to open the URL above and give you the resulting auth token. "
            "Then run the set-token command above.",
            title="🤖 Agent Hint",
            border_style="cyan",
        )
    )


@app.command(name="login")
def login_cmd(
    login_server: str = typer.Option(
        DEFAULT_COGAMES_SERVER,
        "--login-server",
        metavar="URL",
        help="Authentication server URL",
    ),
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
) -> None:
    """Sign in to Softmax."""
    from urllib.parse import urlparse  # noqa: PLC0415

    user_token = None if force else load_cogames_user_token(login_server=login_server)
    if user_token is not None:
        save_cogames_active_token(login_server=login_server, token=user_token)
        console.print(f"Already authenticated with {urlparse(login_server).hostname}", style="green")
        return

    if not sys.stdin.isatty():
        _print_non_tty_login_instructions(login_server=login_server)
        raise typer.Exit(1)

    try:
        do_interactive_login_for_token(
            login_server=login_server,
            server_to_save_token_under=login_server,
            token_kind=TokenKind.COGAMES_USER,
            agent_hint=(
                "If you are a coding agent, ask your human to open the URL below and give you "
                "the auth token. Then paste the token into this window or run:\n"
                "\n"
                f"{_build_manual_set_token_command(login_server=login_server)}"
            ),
            open_browser=not no_browser,
        )
    except Exception as e:
        console.print(f"Error: {e}")
        console.print()
        console.print("Authentication failed.", style="red")
        raise typer.Exit(1) from e

    user_token = load_cogames_user_token(login_server=login_server)
    assert user_token is not None
    save_cogames_active_token(login_server=login_server, token=user_token)
    console.print("Authentication successful.", style="green")


@app.command(name="logout")
def logout_cmd(
    login_server: str = typer.Option(
        DEFAULT_COGAMES_SERVER,
        "--login-server",
        metavar="URL",
        help="Authentication server URL",
    ),
) -> None:
    """Remove saved authentication token."""
    if delete_cogames_tokens(login_server=login_server):
        console.print("Logged out.", style="green")
    else:
        console.print("No token found — already logged out.", style="yellow")


@app.command(name="get-login-url")
def get_login_url_cmd(
    login_server: str = typer.Option(
        DEFAULT_COGAMES_SERVER,
        "--login-server",
        metavar="URL",
        help="Authentication server URL",
    ),
) -> None:
    """Print a browser sign-in URL for manual login."""
    print(build_browser_login_url(login_server))


@app.command(name="status")
def status_cmd(
    login_server: str = typer.Option(
        DEFAULT_COGAMES_SERVER,
        "--login-server",
        metavar="URL",
        help="Authentication server URL",
    ),
    server: str | None = typer.Option(
        None,
        "--server",
        "-s",
        metavar="URL",
        help="API server URL for /whoami verification. Defaults to --login-server when"
        " that is overridden, otherwise the production Observatory API.",
    ),
) -> None:
    """Check authentication status via /whoami."""
    token = load_current_cogames_token(login_server=login_server)
    if not token:
        console.print("[red]Not authenticated.[/red] Run [cyan]softmax login[/cyan] first.")
        raise typer.Exit(1)

    api_server = server or (login_server if login_server != DEFAULT_COGAMES_SERVER else None)
    session = fetch_cogames_whoami(api_server=api_server, token=token)
    console.print("[green]Authenticated[/green]")
    console.print(f"user_email: {session.user_email}")
    console.print(f"subject_type: {session.subject_type}")
    console.print(f"subject_id: {session.subject_id or '-'}")
    console.print(f"owner_user_id: {session.owner_user_id or '-'}")


@app.command(name="get-token")
def get_token_cmd(
    login_server: str = typer.Option(
        DEFAULT_COGAMES_SERVER,
        "--login-server",
        metavar="URL",
        help="Authentication server URL",
    ),
) -> None:
    """Print the saved token to stdout (for scripting)."""
    token = load_current_cogames_token(login_server=login_server)
    if not token:
        console.print("[red]No token found.[/red] Run [cyan]softmax login[/cyan] first.", style="bold")
        raise typer.Exit(1)
    print(token)


@app.command(name="set-token")
def set_token_cmd(
    token: str = typer.Argument(help="Bearer token to save"),
    login_server: str = typer.Option(
        DEFAULT_COGAMES_SERVER,
        "--login-server",
        metavar="URL",
        help="Authentication server URL",
    ),
) -> None:
    """Manually set a token (for CI or headless environments)."""
    save_cogames_user_token(login_server=login_server, token=token)
    print(f"\nToken saved for {login_server}")


_register_optional_apps()
