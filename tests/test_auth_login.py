from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

import softmax.auth as softmax_auth
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

    monkeypatch.setattr("softmax.auth.httpx.Client.get", lambda *args, **kwargs: FakeResponse())

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "subject_type: player" in result.stdout
    assert "subject_id: ply_alpha" in result.stdout
    assert "owner_user_id: regular@example.com" in result.stdout


def test_fetch_whoami_omits_elevated_header_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "user_email": "team@example.com",
                "is_softmax_team_member": False,
                "is_softmax_admin": False,
                "subject_type": "user",
                "subject_id": "user-team-1",
                "owner_user_id": "user-team-1",
                "scopes": [],
            }

    def fake_get(_client, url: str, *, headers: dict[str, str]) -> FakeResponse:
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("softmax.auth.httpx.Client.get", fake_get)

    softmax_auth.fetch_cogames_whoami(api_server="https://softmax.com/api", token="usr_x")

    assert "X-Use-Elevated-Privileges" not in captured["headers"]  # type: ignore[operator]


def test_fetch_whoami_sends_elevated_header_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    """A team member's own CLI token must be able to ask for the privileges it

    already carries (auth.py's `_apply_elevation_gate` treats every request as
    external unless it opts in). Without this header, softmax-cli had no way to
    ever exercise team-gated routes -- not because the token minted the wrong
    identity, but because nothing ever asked for the privileges it already held.
    """
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "user_email": "team@example.com",
                "is_softmax_team_member": True,
                "is_softmax_admin": False,
                "subject_type": "user",
                "subject_id": "user-team-1",
                "owner_user_id": "user-team-1",
                "scopes": [],
            }

    def fake_get(_client, url: str, *, headers: dict[str, str]) -> FakeResponse:
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("softmax.auth.httpx.Client.get", fake_get)

    result = softmax_auth.fetch_cogames_whoami(api_server="https://softmax.com/api", token="usr_x", elevated=True)

    assert captured["headers"]["X-Use-Elevated-Privileges"] == "true"  # type: ignore[index]
    assert result.is_softmax_team_member is True


def test_status_elevated_flag_requests_team_privileges(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_user_token(server="https://softmax.com/api", token="usr_team")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "user_email": "team@example.com",
                "is_softmax_team_member": True,
                "is_softmax_admin": False,
                "subject_type": "user",
                "subject_id": "user-team-1",
                "owner_user_id": "user-team-1",
                "scopes": [],
            }

    def fake_get(_client, url: str, *, headers: dict[str, str]) -> FakeResponse:
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("softmax.auth.httpx.Client.get", fake_get)

    result = runner.invoke(app, ["status", "--elevated"])
    assert result.exit_code == 0
    assert captured["headers"]["X-Use-Elevated-Privileges"] == "true"  # type: ignore[index]


def test_status_without_elevated_flag_does_not_request_team_privileges(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_user_token(server="https://softmax.com/api", token="usr_team")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "user_email": "team@example.com",
                "is_softmax_team_member": False,
                "is_softmax_admin": False,
                "subject_type": "user",
                "subject_id": "user-team-1",
                "owner_user_id": "user-team-1",
                "scopes": [],
            }

    def fake_get(_client, url: str, *, headers: dict[str, str]) -> FakeResponse:
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("softmax.auth.httpx.Client.get", fake_get)

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "X-Use-Elevated-Privileges" not in captured["headers"]  # type: ignore[operator]


def test_status_output_differs_between_elevated_and_non_elevated_for_a_team_member(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Sending the header is not the point -- a person reading `status` output must

    be able to SEE that elevation changed anything. Before this test's fix, the
    printed lines never included is_softmax_team_member/is_softmax_admin at all,
    so a plain run and an `--elevated` run against the same stored token produced
    byte-identical stdout even though the server's answer genuinely differed.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    save_user_token(server="https://softmax.com/api", token="usr_team")

    class FakeResponse:
        def __init__(self, is_team_member: bool) -> None:
            self._is_team_member = is_team_member

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "user_email": "team@example.com",
                "is_softmax_team_member": self._is_team_member,
                "is_softmax_admin": False,
                "subject_type": "user",
                "subject_id": "user-team-1",
                "owner_user_id": "user-team-1",
                "scopes": [],
            }

    def fake_get(_client, url: str, *, headers: dict[str, str]) -> FakeResponse:
        # Mirrors the real server: same stored token, the elevation header is the
        # only thing that flips is_softmax_team_member (auth.py's elevation gate).
        is_team_member = headers.get("X-Use-Elevated-Privileges") == "true"
        return FakeResponse(is_team_member)

    monkeypatch.setattr("softmax.auth.httpx.Client.get", fake_get)

    plain = runner.invoke(app, ["status"])
    elevated = runner.invoke(app, ["status", "--elevated"])

    assert plain.exit_code == 0
    assert elevated.exit_code == 0
    assert plain.stdout != elevated.stdout, "plain and --elevated status output must not be indistinguishable"
    assert "is_softmax_team_member: False" in plain.stdout
    assert "is_softmax_team_member: True" in elevated.stdout


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

    monkeypatch.setattr("softmax.auth.httpx.Client.get", lambda *args, **kwargs: FakeResponse())

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

    monkeypatch.setattr("softmax.auth.httpx.Client.get", lambda *args, **kwargs: FakeResponse())

    result = runner.invoke(app, ["login", "--no-browser"])
    assert "no longer valid" in result.stdout
