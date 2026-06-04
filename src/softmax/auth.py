"""Auth helpers for the softmax CLI: token storage, browser login URL, whoami."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import yaml
from pydantic import BaseModel, Field

DEFAULT_API_SERVER = "https://softmax.com/api"

CREDENTIALS_FILE = "credentials.yaml"


def get_api_server() -> str:
    return os.environ.get("COGAMES_API_URL", DEFAULT_API_SERVER)


# --- on-disk storage ---


def _config_dir() -> Path:
    config_dir = Path.home() / ".softmax"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _credentials_path() -> Path:
    return _config_dir() / CREDENTIALS_FILE


def _load_data() -> dict:
    cred_path = _credentials_path()
    if not cred_path.exists():
        return {"tokens": {}, "player_sessions": {}}

    with open(cred_path, "r") as f:
        return yaml.safe_load(f) or {"tokens": {}, "player_sessions": {}}


def _save_data(data: dict) -> None:
    cred_path = _credentials_path()
    with open(cred_path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)
    os.chmod(cred_path, 0o600)


# --- public token API ---


def load_user_token(*, server: str) -> str | None:
    server = server.rstrip("/")
    tokens = _load_data().get("tokens", {})
    token = tokens.get(server)
    return token if isinstance(token, str) else None


def save_user_token(*, server: str, token: str) -> None:
    server = server.rstrip("/")
    data = _load_data()
    data.setdefault("tokens", {})[server] = token
    _save_data(data)


def _delete_user_token(*, server: str) -> bool:
    server = server.rstrip("/")
    data = _load_data()
    tokens = data.get("tokens", {})
    if server not in tokens:
        return False
    del tokens[server]
    _save_data(data)
    return True


def load_player_session(*, server: str) -> str | None:
    server = server.rstrip("/")
    sessions = _load_data().get("player_sessions", {})
    token = sessions.get(server)
    return token if isinstance(token, str) else None


def save_player_session(*, server: str, token: str) -> None:
    server = server.rstrip("/")
    data = _load_data()
    data.setdefault("player_sessions", {})[server] = token
    _save_data(data)


def _delete_player_session(*, server: str) -> bool:
    server = server.rstrip("/")
    data = _load_data()
    sessions = data.get("player_sessions", {})
    if server not in sessions:
        return False
    del sessions[server]
    _save_data(data)
    return True


def load_current_token(*, server: str) -> str | None:
    """Returns player_session if present, else user token."""
    return load_player_session(server=server) or load_user_token(server=server)


def has_saved_token(*, server: str) -> bool:
    return load_current_token(server=server) is not None


def delete_all_tokens(*, server: str) -> bool:
    deleted_token = _delete_user_token(server=server)
    deleted_session = _delete_player_session(server=server)
    return deleted_token or deleted_session


# --- HTTP / URL helpers ---


class WhoAmIResponse(BaseModel):
    user_email: str
    is_softmax_team_member: bool = False
    is_softmax_admin: bool = False
    subject_type: str = "user"
    subject_id: str | None = None
    owner_user_id: str | None = None
    scopes: list[str] = Field(default_factory=list)


def build_browser_login_url(api_server: str, *, callback_url: str | None = None) -> str:
    """Build the hosted browser sign-in URL for CLI login."""
    params: dict[str, str] = {}
    if callback_url:
        params["callback"] = callback_url

    query = urlencode(params)
    parsed = urlsplit(api_server)
    # Code-exchange flow lives at /cli-auth; the legacy /cli-login route is
    # preserved untouched for published softmax-cli <= 0.26.14 (pinned by
    # coworld[auth]) until those releases age out.
    browser_path = parsed.path.rstrip("/").removesuffix("/api") + "/cli-auth"
    return urlunsplit((parsed.scheme, parsed.netloc, browser_path, query, ""))


def fetch_cogames_whoami(*, api_server: str | None = None, token: str) -> WhoAmIResponse:
    server = api_server or DEFAULT_API_SERVER
    response = httpx.get(
        f"{server.rstrip('/')}/observatory/whoami",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    response.raise_for_status()
    return WhoAmIResponse.model_validate(response.json())


def exchange_auth_code(*, api_server: str, code: str) -> str:
    """Exchange a one-time auth code for a real credential token."""
    response = httpx.post(
        f"{api_server.rstrip('/')}/observatory/credentials/auth-codes/exchange",
        json={"code": code},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["token"]


def format_exchange_error(exc: httpx.HTTPStatusError) -> str:
    status = exc.response.status_code
    if status == 410:
        return (
            "This auth code has already been used or expired. "
            "If you just ran `softmax login`, your token was saved automatically — run `softmax status` to verify."
        )
    if status == 400:
        return "Invalid auth code format."
    return f"Code exchange failed (HTTP {status}): {exc.response.text}"
