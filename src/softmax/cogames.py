from __future__ import annotations

import importlib
from typing import Any

from softmax.auth import DEFAULT_COGAMES_API_SERVER, DEFAULT_COGAMES_SERVER


def _get_tournament_client_class() -> type[Any]:
    try:
        tournament_client_module = importlib.import_module("cogames.cli.client")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "softmax.cogames requires the `cogames` package. Install `softmax-cli[cogames]` or `cogames`."
        ) from exc
    return tournament_client_module.TournamentServerClient


def _create_client(*, token: str, server: str, login_server: str) -> Any:
    client_class = _get_tournament_client_class()
    return client_class(server_url=server, token=token, login_server=login_server)


class _PlayerAPI:
    def list(
        self,
        token: str,
        *,
        server: str = DEFAULT_COGAMES_API_SERVER,
        login_server: str = DEFAULT_COGAMES_SERVER,
    ) -> list[Any]:
        with _create_client(token=token, server=server, login_server=login_server) as client:
            return client.list_players()


player = _PlayerAPI()


def login(
    token: str,
    player_id: str,
    *,
    server: str = DEFAULT_COGAMES_API_SERVER,
    login_server: str = DEFAULT_COGAMES_SERVER,
) -> str:
    with _create_client(token=token, server=server, login_server=login_server) as client:
        return client.login_player(player_id).token


def login_response(
    token: str,
    player_id: str,
    *,
    server: str = DEFAULT_COGAMES_API_SERVER,
    login_server: str = DEFAULT_COGAMES_SERVER,
) -> Any:
    with _create_client(token=token, server=server, login_server=login_server) as client:
        return client.login_player(player_id)


__all__ = ["player", "login", "login_response"]
