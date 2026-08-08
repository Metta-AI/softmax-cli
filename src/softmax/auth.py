"""Auth helpers for the softmax CLI: token storage, browser login URL, whoami."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_API_SERVER = "https://softmax.com/api"

CREDENTIALS_FILE = "credentials.yaml"

# Hosts that exchange_auth_code is willing to send a freshly minted auth code
# to. The exchange step is the only place a real credential leaves the box, so
# this is the trust boundary for the login flow. Other commands (status,
# get-login-url, set-token, ...) are unrestricted so local dev against a custom
# backend still works.
_TRUSTED_HOST_SUFFIXES = (".softmax.com", ".softmax-research.net")
_TRUSTED_EXACT_HOSTS = frozenset({"softmax.com", "localhost", "127.0.0.1", "::1"})


def get_api_server() -> str:
    return os.environ.get("COGAMES_API_URL", DEFAULT_API_SERVER)


class UntrustedApiServerError(Exception):
    """Raised when exchange_auth_code is called against an untrusted host."""


def _is_trusted_exchange_host(api_server: str) -> bool:
    host = (urlsplit(api_server).hostname or "").lower()
    if not host:
        return False
    if host in _TRUSTED_EXACT_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in _TRUSTED_HOST_SUFFIXES)


# --- on-disk storage ---


class CachedPlayerSession(BaseModel):
    token: str
    expires_at: datetime


class ServerPlayerSessions(BaseModel):
    active: str | None = None
    cache: dict[str, CachedPlayerSession] = Field(default_factory=dict)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="allow")

    tokens: dict[str, str] = Field(default_factory=dict)
    player_sessions: dict[str, ServerPlayerSessions] = Field(default_factory=dict)


def _config_dir() -> Path:
    config_dir = Path.home() / ".softmax"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _credentials_path() -> Path:
    return _config_dir() / CREDENTIALS_FILE


def _load_data() -> Credentials:
    cred_path = _credentials_path()
    if not cred_path.exists():
        return Credentials()

    with open(cred_path, "r") as f:
        return Credentials.model_validate(yaml.safe_load(f) or {})


def _save_data(data: Credentials) -> None:
    cred_path = _credentials_path()
    with open(cred_path, "w") as f:
        yaml.safe_dump(data.model_dump(mode="json"), f, default_flow_style=False)
    os.chmod(cred_path, 0o600)


# --- public token API ---


def load_user_token(*, server: str) -> str | None:
    server = server.rstrip("/")
    return _load_data().tokens.get(server)


def save_user_token(*, server: str, token: str) -> None:
    server = server.rstrip("/")
    data = _load_data()
    # Player sessions are owned by whoever held the user token. When the user
    # credential changes (account switch, `login --force`, CI token rotation),
    # the old player sessions belong to the previous user, so drop them rather
    # than letting load_current_token keep acting as that stale player.
    if data.tokens.get(server) != token:
        data.player_sessions.pop(server, None)
    data.tokens[server] = token
    _save_data(data)


# --- player sessions ---
#
# `player_sessions[server]` holds the active player pointer plus a per-player
# token cache so `coworld player use <id>` can re-activate a player without
# re-minting a token until it expires. `load_current_token` returns the active
# player's token when one is selected, so every auth-backed command transparently
# acts as that player. Shape:
#   player_sessions:
#     <server>:
#       active: ply_aaa            # currently selected player id, or absent
#       cache:
#         ply_aaa: {token: ply_..., expires_at: "2026-..."}


def _server_sessions(data: Credentials, server: str) -> ServerPlayerSessions:
    return data.player_sessions.get(server.rstrip("/"), ServerPlayerSessions())


def _store_server_sessions(data: Credentials, server: str, sessions: ServerPlayerSessions) -> None:
    data.player_sessions[server.rstrip("/")] = sessions


def load_player_session(*, server: str) -> str | None:
    """The active player's token, or None when no player is selected or expired.

    Returns None for expired sessions so `load_current_token` falls through to
    the user token rather than sending a dead player token that produces 401s.
    """
    sessions = _server_sessions(_load_data(), server)
    if sessions.active is None:
        return None
    cached = sessions.cache.get(sessions.active)
    if cached is None:
        return None
    if cached.expires_at <= datetime.now(UTC):
        return None
    return cached.token


def get_active_player_id(*, server: str) -> str | None:
    return _server_sessions(_load_data(), server).active


def get_cached_player_session(*, server: str, player_id: str) -> CachedPlayerSession | None:
    return _server_sessions(_load_data(), server).cache.get(player_id)


def set_active_player_session(*, server: str, player_id: str, token: str, expires_at: datetime) -> None:
    data = _load_data()
    sessions = _server_sessions(data, server)
    sessions.cache[player_id] = CachedPlayerSession(token=token, expires_at=expires_at)
    sessions.active = player_id
    _store_server_sessions(data, server, sessions)
    _save_data(data)


def clear_active_player_session(*, server: str) -> bool:
    """Clear the active player pointer, reverting to the user token.

    Keeps the cached tokens so a later `use` of the same player can reuse them.
    Leaves the user token untouched.
    """
    data = _load_data()
    sessions = _server_sessions(data, server)
    if sessions.active is None:
        return False
    sessions.active = None
    _store_server_sessions(data, server, sessions)
    _save_data(data)
    return True


def load_current_token(*, server: str) -> str | None:
    """Returns the active player session token if present, else the user token."""
    return load_player_session(server=server) or load_user_token(server=server)


def has_saved_token(*, server: str) -> bool:
    return load_current_token(server=server) is not None


def delete_all_tokens(*, server: str) -> bool:
    server = server.rstrip("/")
    data = _load_data()
    deleted_token = data.tokens.pop(server, None) is not None
    deleted_session = data.player_sessions.pop(server, None) is not None
    if deleted_token or deleted_session:
        _save_data(data)
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
    if not _is_trusted_exchange_host(api_server):
        host = urlsplit(api_server).hostname or api_server
        raise UntrustedApiServerError(
            f"Refusing to send auth code to untrusted host '{host}'. "
            "Auth codes are only exchanged with softmax.com, *.softmax.com, "
            "*.softmax-research.net, or loopback (localhost / 127.0.0.1)."
        )
    response = httpx.post(
        f"{api_server.rstrip('/')}/observatory/credentials/auth-codes/exchange",
        json={"code": code},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["token"]


def _format_status_error(exc: httpx.HTTPStatusError) -> str:
    status = exc.response.status_code
    if status // 100 == 3:
        return (
            "Failed to exchange auth code due to a redirect. "
            "You may have accidentally pointed --server to the frontend application URL.\n"
            "If you have a valid code, you can still run the following command to exchange it for a token:\n\n"
            "softmax exchange-code <code>"
        )
    if status == 410:
        return (
            "This auth code has already been used or expired. "
            "If you just ran `softmax login`, your token was saved automatically — run `softmax status` to verify."
        )
    if status == 400:
        return "Invalid auth code format."
    return f"Code exchange failed (HTTP {status}): {exc.response.text}"


class ExchangeSuccess(BaseModel):
    token: str


class ExchangeFailure(BaseModel):
    message: str


ExchangeOutcome = ExchangeSuccess | ExchangeFailure


def try_exchange_auth_code(*, api_server: str, code: str) -> ExchangeOutcome:
    """Exchange an auth code, returning a typed success/failure result.

    Centralizes the error-classification ladder so every callsite (CLI command,
    manual-paste loop, callback handler) gets the same message without repeating
    try/except blocks.
    """
    try:
        token = exchange_auth_code(api_server=api_server, code=code)
    except UntrustedApiServerError as exc:
        return ExchangeFailure(message=str(exc))
    except httpx.HTTPStatusError as exc:
        return ExchangeFailure(message=_format_status_error(exc))
    except httpx.HTTPError:
        return ExchangeFailure(
            message=(
                "Could not exchange auth code. Check that --server points at the API "
                "(e.g. https://softmax.com/api) and try again."
            ),
        )
    return ExchangeSuccess(token=token)
