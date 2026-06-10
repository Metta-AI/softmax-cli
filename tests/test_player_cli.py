from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pytest_httpserver import HTTPServer
from typer.testing import CliRunner

from softmax.auth import (
    clear_active_player_session,
    get_active_player_id,
    load_current_token,
    load_player_session,
    load_user_token,
    save_user_token,
    set_active_player_session,
)
from softmax.cli import app

PLAYER_ALPHA = {
    "id": "ply_00000000-0000-0000-0000-0000000000a1",
    "name": "Alpha",
    "is_default": True,
    "avatar_url": None,
    "created_at": "2026-06-05T12:00:00Z",
    "disabled_at": None,
    "user_id": "usr_owner",
}
PLAYER_BETA = {
    "id": "ply_00000000-0000-0000-0000-0000000000b2",
    "name": "Beta",
    "is_default": False,
    "avatar_url": None,
    "created_at": "2026-06-06T12:00:00Z",
    "disabled_at": None,
    "user_id": "usr_owner",
}


@pytest.fixture(autouse=True)
def _sandbox_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # Isolate ~/.softmax/credentials.yaml under tmp.
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture
def _mock_user_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub the user token for commands that authenticate against the API. Tests
    # that assert on real token storage seed it via save_user_token instead.
    monkeypatch.setattr("softmax.auth.load_user_token", lambda *, server: "user-token")


def _activate(server: str, player_id: str, token: str = "ply_session", hours: int = 24) -> None:
    set_active_player_session(
        server=server,
        player_id=player_id,
        token=token,
        expires_at=datetime.now(UTC) + timedelta(hours=hours),
    )


def test_list_marks_active(httpserver: HTTPServer, _mock_user_auth: None) -> None:
    server = httpserver.url_for("")
    _activate(server, PLAYER_BETA["id"])
    httpserver.expect_request(
        "/observatory/players",
        method="GET",
        headers={"Authorization": "Bearer user-token"},
    ).respond_with_json([PLAYER_ALPHA, PLAYER_BETA])

    result = CliRunner().invoke(app, ["player", "list", "--server", server])

    assert result.exit_code == 0, result.output
    assert "Alpha" in result.output
    assert "Beta" in result.output
    # The active marker renders on the Beta row.
    assert "●" in result.output


def test_list_json_includes_active_flag(httpserver: HTTPServer, _mock_user_auth: None) -> None:
    server = httpserver.url_for("")
    _activate(server, PLAYER_ALPHA["id"])
    httpserver.expect_request("/observatory/players", method="GET").respond_with_json([PLAYER_ALPHA, PLAYER_BETA])

    result = CliRunner().invoke(app, ["player", "list", "--server", server, "--json"])

    assert result.exit_code == 0, result.output
    entries = json.loads(result.output)
    by_id = {e["id"]: e["active"] for e in entries}
    assert by_id[PLAYER_ALPHA["id"]] is True
    assert by_id[PLAYER_BETA["id"]] is False


def test_use_mints_and_activates(httpserver: HTTPServer, _mock_user_auth: None) -> None:
    server = httpserver.url_for("")
    expires_at = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    httpserver.expect_request(
        "/observatory/players",
        method="GET",
        headers={"Authorization": "Bearer user-token"},
    ).respond_with_json([PLAYER_ALPHA, PLAYER_BETA])
    httpserver.expect_request(
        f"/observatory/players/{PLAYER_BETA['id']}/login",
        method="POST",
        headers={"Authorization": "Bearer user-token"},
    ).respond_with_json({"player_id": PLAYER_BETA["id"], "token": "ply_minted", "expires_at": expires_at})

    result = CliRunner().invoke(app, ["player", "use", PLAYER_BETA["id"], "--server", server])

    assert result.exit_code == 0, result.output
    assert get_active_player_id(server=server) == PLAYER_BETA["id"]
    assert load_player_session(server=server) == "ply_minted"


def test_use_reuses_cached_token_without_network(httpserver: HTTPServer) -> None:
    server = httpserver.url_for("")
    # Pre-seed a fresh cached session, then unset so it stays cached but inactive.
    _activate(server, PLAYER_BETA["id"], token="ply_cached")
    clear_active_player_session(server=server)

    result = CliRunner().invoke(app, ["player", "use", PLAYER_BETA["id"], "--server", server])

    assert result.exit_code == 0, result.output
    assert "cached session" in result.output
    assert get_active_player_id(server=server) == PLAYER_BETA["id"]
    assert load_player_session(server=server) == "ply_cached"
    # No HTTP traffic should have hit the server.
    assert httpserver.log == []


def test_use_unknown_id_errors_without_login(httpserver: HTTPServer, _mock_user_auth: None) -> None:
    server = httpserver.url_for("")
    httpserver.expect_request("/observatory/players", method="GET").respond_with_json([PLAYER_ALPHA])

    result = CliRunner().invoke(app, ["player", "use", "ply_does_not_exist", "--server", server])

    assert result.exit_code == 1, result.output
    assert "not found" in result.output
    # Only the list request was made; no login was attempted.
    assert all("/login" not in request.path for request, _ in httpserver.log)


def test_unset_clears_active_keeps_user_token(httpserver: HTTPServer) -> None:
    server = httpserver.url_for("")
    save_user_token(server=server, token="user-token")
    _activate(server, PLAYER_ALPHA["id"])

    result = CliRunner().invoke(app, ["player", "unset", "--server", server])

    assert result.exit_code == 0, result.output
    assert "Reverted" in result.output
    assert load_player_session(server=server) is None
    assert load_user_token(server=server) == "user-token"


def test_unset_when_no_active_player(httpserver: HTTPServer) -> None:
    server = httpserver.url_for("")

    result = CliRunner().invoke(app, ["player", "unset", "--server", server])

    assert result.exit_code == 0, result.output
    assert "No active player" in result.output


def test_active_player_inherited_by_load_current_token(httpserver: HTTPServer, _mock_user_auth: None) -> None:
    server = httpserver.url_for("")
    expires_at = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    httpserver.expect_request("/observatory/players", method="GET").respond_with_json([PLAYER_ALPHA])
    httpserver.expect_request(f"/observatory/players/{PLAYER_ALPHA['id']}/login", method="POST").respond_with_json(
        {"player_id": PLAYER_ALPHA["id"], "token": "ply_minted", "expires_at": expires_at}
    )

    result = CliRunner().invoke(app, ["player", "use", PLAYER_ALPHA["id"], "--server", server])
    assert result.exit_code == 0, result.output

    # Other commands resolve their token via load_current_token, which must now
    # return the active player token.
    assert load_current_token(server=server) == "ply_minted"
