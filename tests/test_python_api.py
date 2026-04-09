from __future__ import annotations

import importlib
import sys
from typing import Any, cast

import pytest

import softmax
import softmax.cogames as softmax_cogames
from softmax.auth import load_token
from softmax.token_storage import TokenKind, save_token


def test_login_returns_saved_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_token(token_kind=TokenKind.COGAMES_USER, server="https://softmax.com/api", token="saved-token")

    called = {"interactive": False}
    monkeypatch.setattr(
        "softmax.do_interactive_login_for_token",
        lambda **_: called.__setitem__("interactive", True),
    )

    assert softmax.login() == "saved-token"
    assert load_token(token_kind=TokenKind.COGAMES, server="https://softmax.com/api") == "saved-token"
    assert called["interactive"] is False


def test_login_runs_interactive_flow_when_missing_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def fake_login(**_: object) -> None:
        save_token(token_kind=TokenKind.COGAMES_USER, server="https://softmax.com/api", token="fresh-token")

    monkeypatch.setattr("softmax.do_interactive_login_for_token", fake_login)

    assert softmax.login() == "fresh-token"
    assert load_token(token_kind=TokenKind.COGAMES, server="https://softmax.com/api") == "fresh-token"


def test_login_ignores_active_only_token_without_saved_user_session(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    save_token(token_kind=TokenKind.COGAMES, server="https://softmax.com/api", token="active-only-token")

    called = {"interactive": False}

    def fake_login(**_: object) -> None:
        called["interactive"] = True
        save_token(token_kind=TokenKind.COGAMES_USER, server="https://softmax.com/api", token="fresh-token")

    monkeypatch.setattr("softmax.do_interactive_login_for_token", fake_login)

    assert softmax.login() == "fresh-token"
    assert load_token(token_kind=TokenKind.COGAMES, server="https://softmax.com/api") == "fresh-token"
    assert called["interactive"] is True


def test_login_requires_tty_when_missing_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(RuntimeError, match="interactive login requires a TTY"):
        softmax.login()


def test_softmax_module_exposes_cogames_submodule() -> None:
    assert cast(Any, softmax).cogames is importlib.import_module("softmax.cogames")


def test_softmax_cogames_player_list_uses_expected_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, server_url: str, token: str, login_server: str) -> None:
            captured["server_url"] = server_url
            captured["token"] = token
            captured["login_server"] = login_server

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def list_players(self) -> list[str]:
            return ["alpha", "beta"]

    monkeypatch.setattr(softmax_cogames, "_get_tournament_client_class", lambda: FakeClient)

    assert cast(Any, softmax).cogames.player.list("softmax-token") == ["alpha", "beta"]
    assert captured == {
        "server_url": "https://api.observatory.softmax-research.net",
        "token": "softmax-token",
        "login_server": "https://softmax.com/api",
    }


def test_softmax_cogames_login_returns_player_token(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLoginResponse:
        token = "player-token"

    class FakeClient:
        def __init__(self, *, server_url: str, token: str, login_server: str) -> None:
            self.server_url = server_url
            self.token = token
            self.login_server = login_server

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def login_player(self, player_id: str) -> FakeLoginResponse:
            assert self.server_url == "https://api.observatory.softmax-research.net"
            assert self.token == "softmax-token"
            assert self.login_server == "https://softmax.com/api"
            assert player_id == "ply_alpha"
            return FakeLoginResponse()

    monkeypatch.setattr(softmax_cogames, "_get_tournament_client_class", lambda: FakeClient)

    assert cast(Any, softmax).cogames.login("softmax-token", "ply_alpha") == "player-token"


def test_softmax_cogames_login_response_returns_full_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLoginResponse:
        token = "player-token"
        expires_at = "2026-02-21T12:00:00Z"

    class FakeClient:
        def __init__(self, *, server_url: str, token: str, login_server: str) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def login_player(self, player_id: str) -> FakeLoginResponse:
            assert player_id == "ply_alpha"
            return FakeLoginResponse()

    monkeypatch.setattr(softmax_cogames, "_get_tournament_client_class", lambda: FakeClient)

    response = cast(Any, softmax).cogames.login_response("softmax-token", "ply_alpha")
    assert response.token == "player-token"
    assert response.expires_at == "2026-02-21T12:00:00Z"


def test_login_can_force_refresh_existing_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_token(token_kind=TokenKind.COGAMES_USER, server="https://softmax.com/api", token="old-token")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def fake_login(**_: object) -> None:
        save_token(token_kind=TokenKind.COGAMES_USER, server="https://softmax.com/api", token="new-token")

    monkeypatch.setattr("softmax.do_interactive_login_for_token", fake_login)

    assert softmax.login(force=True) == "new-token"
    assert load_token(token_kind=TokenKind.COGAMES, server="https://softmax.com/api") == "new-token"


def test_login_restores_saved_user_session_over_active_player_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_token(token_kind=TokenKind.COGAMES, server="https://softmax.com/api", token="player-token")
    save_token(token_kind=TokenKind.COGAMES_USER, server="https://softmax.com/api", token="user-token")

    called = {"interactive": False}
    monkeypatch.setattr(
        "softmax.do_interactive_login_for_token",
        lambda **_: called.__setitem__("interactive", True),
    )

    assert softmax.login() == "user-token"
    assert load_token(token_kind=TokenKind.COGAMES, server="https://softmax.com/api") == "user-token"
    assert called["interactive"] is False
