"""Token storage and browser URL helpers for CLI auth."""

from __future__ import annotations

import os
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, Field

from softmax.token_storage import TokenKind
from softmax.token_storage import delete_token as delete_stored_token
from softmax.token_storage import load_token as load_saved_token
from softmax.token_storage import save_token as save_stored_token

DEFAULT_API_SERVER = "https://softmax.com/api"


def get_api_server() -> str:
    return os.environ.get("COGAMES_API_URL", DEFAULT_API_SERVER)


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
    browser_path = parsed.path.rstrip("/").removesuffix("/api") + "/cli-login"
    return urlunsplit((parsed.scheme, parsed.netloc, browser_path, query, ""))


def load_token(*, token_kind: TokenKind, server: str) -> str | None:
    return load_saved_token(token_kind=token_kind, server=server)


def has_saved_token(*, token_kind: TokenKind, server: str) -> bool:
    return load_token(token_kind=token_kind, server=server) is not None


def save_token(*, token_kind: TokenKind, server: str, token: str) -> None:
    save_stored_token(token_kind=token_kind, server=server, token=token)


def delete_token(*, token_kind: TokenKind, server: str) -> bool:
    return delete_stored_token(token_kind=token_kind, server=server)


def load_cogames_user_token(*, api_server: str) -> str | None:
    return load_token(token_kind=TokenKind.COGAMES_USER, server=api_server)


def load_current_cogames_token(*, api_server: str) -> str | None:
    return load_token(token_kind=TokenKind.COGAMES, server=api_server) or load_cogames_user_token(api_server=api_server)


def save_cogames_active_token(*, api_server: str, token: str) -> None:
    save_token(token_kind=TokenKind.COGAMES, server=api_server, token=token)


def save_cogames_user_token(*, api_server: str, token: str) -> None:
    save_token(token_kind=TokenKind.COGAMES_USER, server=api_server, token=token)
    save_cogames_active_token(api_server=api_server, token=token)


def delete_cogames_tokens(*, api_server: str) -> bool:
    deleted_active = delete_token(token_kind=TokenKind.COGAMES, server=api_server)
    deleted_user = delete_token(token_kind=TokenKind.COGAMES_USER, server=api_server)
    return deleted_active or deleted_user


def fetch_cogames_whoami(*, api_server: str | None = None, token: str) -> WhoAmIResponse:
    server = api_server or DEFAULT_API_SERVER
    response = httpx.get(
        f"{server.rstrip('/')}/observatory/whoami",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    response.raise_for_status()
    return WhoAmIResponse.model_validate(response.json())


def restore_cogames_user_session(*, api_server: str) -> str | None:
    user_token = load_cogames_user_token(api_server=api_server)
    if user_token is None:
        return None
    save_cogames_active_token(api_server=api_server, token=user_token)
    return user_token
