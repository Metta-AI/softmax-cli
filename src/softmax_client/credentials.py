"""Saved user credentials and active player sessions."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

CREDENTIALS_FILE = "credentials.yaml"
CONFIG_DIR_ENV = "SOFTMAX_CONFIG_DIR"


class CachedPlayerSession(BaseModel):
    model_config = ConfigDict(extra="allow")

    token: str
    expires_at: datetime


class ServerPlayerSessions(BaseModel):
    model_config = ConfigDict(extra="allow")

    active: str | None = None
    cache: dict[str, CachedPlayerSession] = Field(default_factory=dict)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="allow")

    tokens: dict[str, str] = Field(default_factory=dict)
    player_sessions: dict[str, ServerPlayerSessions] = Field(default_factory=dict)


def _config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".softmax"


def _credentials_path() -> Path:
    config_dir = _config_dir()
    config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    return config_dir / CREDENTIALS_FILE


def _load_data() -> Credentials:
    cred_path = _credentials_path()
    if not cred_path.exists():
        return Credentials()

    with open(cred_path) as f:
        return Credentials.model_validate(yaml.safe_load(f) or {})


def _save_data(data: Credentials) -> None:
    cred_path = _credentials_path()
    temporary = tempfile.NamedTemporaryFile(mode="w", dir=cred_path.parent, prefix=".credentials-", delete=False)
    try:
        with temporary:
            yaml.safe_dump(data.model_dump(mode="json"), temporary, default_flow_style=False)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary.name, cred_path)
    finally:
        Path(temporary.name).unlink(missing_ok=True)


def load_user_token(*, server: str) -> str | None:
    server = server.rstrip("/")
    return _load_data().tokens.get(server)


def save_user_token(*, server: str, token: str) -> None:
    server = server.rstrip("/")
    data = _load_data()
    # Changing the account credential invalidates every cached player session owned by that account.
    if data.tokens.get(server) != token:
        data.player_sessions.pop(server, None)
    data.tokens[server] = token
    _save_data(data)


def _server_sessions(data: Credentials, server: str) -> ServerPlayerSessions:
    return data.player_sessions.get(server.rstrip("/"), ServerPlayerSessions())


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
    if player_id in sessions.cache:
        sessions.cache[player_id].token = token
        sessions.cache[player_id].expires_at = expires_at
    else:
        sessions.cache[player_id] = CachedPlayerSession(token=token, expires_at=expires_at)
    sessions.active = player_id
    data.player_sessions[server.rstrip("/")] = sessions
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
    data.player_sessions[server.rstrip("/")] = sessions
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
