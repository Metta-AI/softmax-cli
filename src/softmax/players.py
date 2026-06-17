"""Player identity management: list players and switch the active player session.

A player is an identity owned by your Softmax user. Activating one stores a 24h
player session in ~/.softmax/credentials.yaml; `load_current_token` then returns
the player token, so every auth-backed command in any CLI built on softmax-cli
(`softmax`, `coworld`, ...) transparently acts as that player.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import typer
from pydantic import BaseModel, ConfigDict
from rich import box
from rich.table import Table

from softmax import auth
from softmax._console import console
from softmax.auth import DEFAULT_API_SERVER


class PlayerResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str  # ply_<uuid>
    name: str
    is_default: bool = False
    avatar_url: str | None = None
    created_at: datetime
    disabled_at: datetime | None = None
    user_id: str | None = None


class PlayerLoginResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    player_id: str
    token: str
    expires_at: datetime


def list_players(*, server: str, token: str) -> list[PlayerResponse]:
    response = httpx.get(
        f"{server.rstrip('/')}/observatory/players",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    response.raise_for_status()
    return [PlayerResponse.model_validate(entry) for entry in response.json()]


def create_player(*, server: str, token: str, name: str) -> PlayerResponse:
    response = httpx.post(
        f"{server.rstrip('/')}/observatory/players",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
        timeout=10.0,
    )
    response.raise_for_status()
    return PlayerResponse.model_validate(response.json())


def login_player(*, server: str, token: str, player_id: str) -> PlayerLoginResponse:
    response = httpx.post(
        f"{server.rstrip('/')}/observatory/players/{player_id}/login",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    response.raise_for_status()
    return PlayerLoginResponse.model_validate(response.json())


def _user_token(server: str) -> str:
    # Player routes require a real user identity (USER_AUTH) and reject
    # player-scoped tokens, so resolve the user token directly rather than
    # load_current_token, which would pick up the active player session.
    token = auth.load_user_token(server=server)
    if token is None:
        raise RuntimeError(f"Not authenticated. Run: softmax login --server {server}")
    return token


player_app = typer.Typer(no_args_is_help=True, help="Manage the active player identity.")


@player_app.command("list")
def player_list(
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print raw JSON.")] = False,
) -> None:
    active_id = auth.get_active_player_id(server=server)
    players = list_players(server=server, token=_user_token(server))
    if json_output:
        payload = [{**p.model_dump(mode="json"), "active": p.id == active_id} for p in players]
        print(json.dumps(payload, indent=2))
        return
    table = Table(box=box.SIMPLE_HEAVY, show_lines=False, pad_edge=False)
    table.add_column("")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Default")
    for p in players:
        is_active = p.id == active_id
        marker = "[green]●[/green]" if is_active else ""
        name = f"[bold]{p.name}[/bold]" if is_active else p.name
        table.add_row(marker, p.id, name, "yes" if p.is_default else "no")
    console.print(table)
    if active_id is None:
        console.print("[dim]No active player; commands act as your main user.[/dim]")


@player_app.command("create")
def player_create(
    name: Annotated[str, typer.Argument(help="Name for the new player.")],
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
    json_output: Annotated[bool, typer.Option("--json", help="Print raw JSON.")] = False,
) -> None:
    player = create_player(server=server, token=_user_token(server), name=name)
    if json_output:
        print(json.dumps(player.model_dump(mode="json"), indent=2))
        return
    console.print(f"[green]Created player[/green] [bold]{player.name}[/bold] ({player.id})")


@player_app.command("use")
def player_use(
    player_id: Annotated[str, typer.Argument(help="Player ID (ply_...) to act as.")],
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
) -> None:
    # Reuse a cached, non-expired session rather than minting a fresh token.
    cached = auth.get_cached_player_session(server=server, player_id=player_id)
    if cached is not None and cached.expires_at - timedelta(minutes=5) > datetime.now(UTC):
        auth.set_active_player_session(
            server=server, player_id=player_id, token=cached.token, expires_at=cached.expires_at
        )
        console.print(f"[green]Active player set to[/green] [bold]{player_id}[/bold] [dim](cached session)[/dim]")
        return

    token = _user_token(server)
    players = list_players(server=server, token=token)
    match = next((p for p in players if p.id == player_id), None)
    if match is None:
        console.print(f"[red]Player '{player_id}' not found in your account.[/red]")
        raise typer.Exit(1)
    login = login_player(server=server, token=token, player_id=player_id)
    auth.set_active_player_session(server=server, player_id=player_id, token=login.token, expires_at=login.expires_at)
    console.print(f"[green]Active player set to[/green] [bold]{match.name}[/bold] ({player_id})")
    console.print(f"[dim]Session expires:[/dim] {login.expires_at.isoformat()}")


@player_app.command("unset")
def player_unset(
    server: Annotated[str, typer.Option("--server", help="API server URL.")] = DEFAULT_API_SERVER,
) -> None:
    if auth.clear_active_player_session(server=server):
        console.print("[green]Reverted to your main user credential.[/green]")
    else:
        console.print("[yellow]No active player was set.[/yellow]")
