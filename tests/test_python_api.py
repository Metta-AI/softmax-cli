from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from pydantic import ValidationError

import softmax
import softmax.auth as auth
from softmax.auth import (
    clear_active_player_session,
    get_cached_player_session,
    load_current_token,
    load_player_session,
    load_user_token,
    save_user_token,
    set_active_player_session,
)


def _activate_player(server: str, token: str, player_id: str = "ply_alpha") -> None:
    set_active_player_session(
        server=server,
        player_id=player_id,
        token=token,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )


@pytest.mark.parametrize(
    "credentials",
    [
        {"tokens": {"https://softmax.com/api": 123}},
        {
            "player_sessions": {
                "https://softmax.com/api": {"active": ["ply_alpha"], "cache": {}},
            },
        },
    ],
)
def test_malformed_credentials_fail_validation(monkeypatch: pytest.MonkeyPatch, tmp_path, credentials) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_dir = tmp_path / ".softmax"
    config_dir.mkdir()
    (config_dir / "credentials.yaml").write_text(yaml.safe_dump(credentials))

    with pytest.raises(ValidationError):
        auth._load_data()


def test_unknown_credential_fields_survive_save(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_dir = tmp_path / ".softmax"
    config_dir.mkdir()
    credentials_path = config_dir / "credentials.yaml"
    credentials_path.write_text(yaml.safe_dump({"credential_version": {"major": 2}}))

    save_user_token(server="https://softmax.com/api", token="user-token")

    saved = yaml.safe_load(credentials_path.read_text())
    assert saved["credential_version"] == {"major": 2}


def test_delete_all_tokens_is_one_credentials_update(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    server = "https://softmax.com/api"
    save_user_token(server=server, token="user-token")
    _activate_player(server, "player-token")
    credentials = auth._load_data()
    calls = {"loads": 0, "saves": 0}

    def load() -> auth.Credentials:
        calls["loads"] += 1
        return credentials

    def save(data: auth.Credentials) -> None:
        calls["saves"] += 1
        assert data is credentials

    monkeypatch.setattr(auth, "_load_data", load)
    monkeypatch.setattr(auth, "_save_data", save)

    assert auth.delete_all_tokens(server=server) is True
    assert calls == {"loads": 1, "saves": 1}
    assert server not in credentials.tokens
    assert server not in credentials.player_sessions


def test_login_returns_saved_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_user_token(server="https://softmax.com/api", token="saved-token")

    called = {"interactive": False}
    monkeypatch.setattr(
        "softmax.do_interactive_login_for_token",
        lambda **_: called.__setitem__("interactive", True),
    )

    assert softmax.login() == "saved-token"
    assert load_user_token(server="https://softmax.com/api") == "saved-token"
    assert called["interactive"] is False


def test_login_runs_interactive_flow_when_missing_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def fake_login(**_: object) -> None:
        save_user_token(server="https://softmax.com/api", token="fresh-token")

    monkeypatch.setattr("softmax.do_interactive_login_for_token", fake_login)

    assert softmax.login() == "fresh-token"
    assert load_user_token(server="https://softmax.com/api") == "fresh-token"


def test_login_ignores_player_session_without_saved_user_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    _activate_player("https://softmax.com/api", "active-only-token")

    called = {"interactive": False}

    def fake_login(**_: object) -> None:
        called["interactive"] = True
        save_user_token(server="https://softmax.com/api", token="fresh-token")

    monkeypatch.setattr("softmax.do_interactive_login_for_token", fake_login)

    assert softmax.login() == "fresh-token"
    assert load_user_token(server="https://softmax.com/api") == "fresh-token"
    assert called["interactive"] is True


def test_login_requires_tty_when_missing_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(RuntimeError, match="interactive login requires a TTY"):
        softmax.login()


def test_login_can_force_refresh_existing_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_user_token(server="https://softmax.com/api", token="old-token")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def fake_login(**_: object) -> None:
        save_user_token(server="https://softmax.com/api", token="new-token")

    monkeypatch.setattr("softmax.do_interactive_login_for_token", fake_login)

    assert softmax.login(force=True) == "new-token"
    assert load_user_token(server="https://softmax.com/api") == "new-token"


def test_login_returns_user_token_even_with_active_player_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _activate_player("https://softmax.com/api", "player-token")
    save_user_token(server="https://softmax.com/api", token="user-token")

    called = {"interactive": False}
    monkeypatch.setattr(
        "softmax.do_interactive_login_for_token",
        lambda **_: called.__setitem__("interactive", True),
    )

    assert softmax.login() == "user-token"
    assert load_user_token(server="https://softmax.com/api") == "user-token"
    assert called["interactive"] is False


def test_set_and_clear_active_player_session_preserves_user_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    server = "https://softmax.com/api"
    save_user_token(server=server, token="user-token")
    _activate_player(server, "player-token", player_id="ply_alpha")

    assert load_player_session(server=server) == "player-token"

    assert clear_active_player_session(server=server) is True
    # Active pointer is gone, so the user token is what's current again.
    assert load_player_session(server=server) is None
    assert load_user_token(server=server) == "user-token"
    # The cached player token survives for a fast re-activation.
    cached = get_cached_player_session(server=server, player_id="ply_alpha")
    assert cached is not None
    assert cached.token == "player-token"

    # Clearing again is a no-op.
    assert clear_active_player_session(server=server) is False


def test_changing_user_token_drops_player_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    server = "https://softmax.com/api"
    save_user_token(server=server, token="user-token")
    _activate_player(server, "player-token", player_id="ply_alpha")
    assert load_current_token(server=server) == "player-token"

    # Re-saving the same token must NOT disturb the active player session.
    save_user_token(server=server, token="user-token")
    assert load_current_token(server=server) == "player-token"

    # Switching the user credential invalidates the old user's player sessions,
    # so commands act as the new user rather than the stale player.
    save_user_token(server=server, token="new-user-token")
    assert load_player_session(server=server) is None
    assert get_cached_player_session(server=server, player_id="ply_alpha") is None
    assert load_current_token(server=server) == "new-user-token"


def test_expired_player_session_falls_through_to_user_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    server = "https://softmax.com/api"
    save_user_token(server=server, token="user-token")

    # Activate a player with an already-expired session.
    set_active_player_session(
        server=server,
        player_id="ply_alpha",
        token="expired-player-token",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    # The active pointer is set, but load_player_session skips the expired token.
    assert load_player_session(server=server) is None
    # load_current_token falls through to the user token.
    assert load_current_token(server=server) == "user-token"
