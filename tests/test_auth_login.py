from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

import softmax.perform_login as auth_module
from softmax.auth import build_browser_login_url, load_user_token, save_user_token, set_active_player_session
from softmax.cli import _build_manual_exchange_command, app
from softmax.perform_login import do_interactive_login_for_token

runner = CliRunner()


def _activate_player(server: str, token: str, player_id: str = "ply_alpha") -> None:
    set_active_player_session(
        server=server,
        player_id=player_id,
        token=token,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )


def test_authenticate_exchanges_code_via_callback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("softmax.perform_login._find_free_port", lambda: 43123)
    monkeypatch.setattr("softmax.perform_login._run_server", lambda *, session, port, api_server: None)
    monkeypatch.setattr("softmax.perform_login._wait_for_callback_server_to_start", lambda *, session, port: False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    monkeypatch.setattr(
        "softmax.perform_login._start_manual_code_prompt",
        lambda *, session, api_server: auth_module._finish_authentication(session, token="usr_exchanged-token"),
    )

    do_interactive_login_for_token(
        api_server="https://softmax.com/api",
        agent_hint=None,
        open_browser=False,
    )
    assert load_user_token(server="https://softmax.com/api") == "usr_exchanged-token"


def test_authenticate_skips_browser_when_requested(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    opened = {"called": False}

    monkeypatch.setattr("softmax.perform_login._find_free_port", lambda: 43124)
    monkeypatch.setattr("softmax.perform_login._run_server", lambda *, session, port, api_server: None)
    monkeypatch.setattr(
        "softmax.perform_login._wait_for_callback_server_to_start",
        lambda *, session, port: False,
    )
    monkeypatch.setattr(
        "softmax.perform_login._open_browser",
        lambda *, url: opened.__setitem__("called", True) or True,
    )
    monkeypatch.setattr(
        "softmax.perform_login._start_manual_code_prompt",
        lambda *, session, api_server: auth_module._finish_authentication(session, token="usr_manual-456"),
    )

    do_interactive_login_for_token(
        api_server="https://softmax.com/api",
        agent_hint=None,
        open_browser=False,
    )
    assert opened["called"] is False


def test_authenticate_falls_back_to_manual_when_callback_server_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    captured_urls: list[str] = []

    monkeypatch.setattr("softmax.perform_login._find_free_port", lambda: 43125)
    monkeypatch.setattr(
        "softmax.perform_login._wait_for_callback_server_to_start",
        lambda *, session, port: False,
    )
    monkeypatch.setattr("softmax.perform_login._run_server", lambda *, session, port, api_server: None)
    monkeypatch.setattr(
        "softmax.perform_login._open_browser",
        lambda *, url: captured_urls.append(url) or True,
    )
    monkeypatch.setattr(
        "softmax.perform_login._start_manual_code_prompt",
        lambda *, session, api_server: auth_module._finish_authentication(session, token="usr_manual-789"),
    )

    do_interactive_login_for_token(
        api_server="https://softmax.com/api",
        agent_hint=None,
        open_browser=True,
    )
    assert captured_urls == ["https://softmax.com/cli-auth"]


def test_manual_command_format() -> None:
    assert _build_manual_exchange_command() == "softmax exchange-code '<CODE>'"
    assert (
        _build_manual_exchange_command("https://custom.server/api")
        == "softmax exchange-code --server 'https://custom.server/api' '<CODE>'"
    )


def test_build_browser_login_url_uses_cli_auth_path() -> None:
    assert build_browser_login_url("https://softmax.com/api") == "https://softmax.com/cli-auth"
    assert (
        build_browser_login_url(
            "https://softmax.com/api",
            callback_url="http://127.0.0.1:5555/callback",
        )
        == "https://softmax.com/cli-auth?callback=http%3A%2F%2F127.0.0.1%3A5555%2Fcallback"
    )


def test_status_prints_active_subject_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _activate_player("https://softmax.com/api", "player-session-token")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "user_email": "regular@example.com",
                "is_softmax_team_member": False,
                "is_softmax_admin": False,
                "subject_type": "player",
                "subject_id": "ply_alpha",
                "owner_user_id": "regular@example.com",
                "scopes": [],
            }

    monkeypatch.setattr("softmax.auth.httpx.get", lambda *args, **kwargs: FakeResponse())

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "subject_type: player" in result.stdout
    assert "subject_id: ply_alpha" in result.stdout
    assert "owner_user_id: regular@example.com" in result.stdout


def test_interactive_login_requires_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(AssertionError, match="only be called when stdin is a TTY"):
        do_interactive_login_for_token(
            api_server="https://softmax.com/api",
            agent_hint=None,
            open_browser=False,
        )


def test_load_token_returns_none_for_empty_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert load_user_token(server="https://softmax.com/api") is None


def test_status_fails_for_anonymous_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_user_token(server="https://softmax.com/api", token="bad-token")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "user_email": "unknown",
                "is_softmax_team_member": False,
                "is_softmax_admin": False,
                "subject_type": "anonymous",
                "subject_id": None,
                "owner_user_id": None,
                "scopes": [],
            }

    monkeypatch.setattr("softmax.auth.httpx.get", lambda *args, **kwargs: FakeResponse())

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "invalid or expired" in result.stdout


def test_login_detects_anonymous_whoami_as_invalid_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_user_token(server="https://softmax.com/api", token="stale-token")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "user_email": "unknown",
                "is_softmax_team_member": False,
                "is_softmax_admin": False,
                "subject_type": "anonymous",
                "subject_id": None,
                "owner_user_id": None,
                "scopes": [],
            }

    monkeypatch.setattr("softmax.auth.httpx.get", lambda *args, **kwargs: FakeResponse())

    result = runner.invoke(app, ["login", "--no-browser"])
    assert "no longer valid" in result.stdout
