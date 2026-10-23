"""Typed player identities and explicit-token player requests."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from softmax_client.http import observatory_client


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


def list_players(*, server: str, token: str, product: str = "softmax-cli") -> list[PlayerResponse]:
    with observatory_client(server=server, token=token, product=product) as client:
        response = client.get("/players")
    response.raise_for_status()
    return [PlayerResponse.model_validate(entry) for entry in response.json()]


def create_player(*, server: str, token: str, name: str, product: str = "softmax-cli") -> PlayerResponse:
    with observatory_client(server=server, token=token, product=product) as client:
        response = client.post("/players", json={"name": name})
    response.raise_for_status()
    return PlayerResponse.model_validate(response.json())


def login_player(*, server: str, token: str, player_id: str, product: str = "softmax-cli") -> PlayerLoginResponse:
    with observatory_client(server=server, token=token, product=product) as client:
        response = client.post(f"/players/{player_id}/login")
    response.raise_for_status()
    return PlayerLoginResponse.model_validate(response.json())
