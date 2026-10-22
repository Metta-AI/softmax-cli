"""Softmax sign-in URLs, code exchange and account identity."""

from __future__ import annotations

import os
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, Field

from softmax_client.agent import user_agent
from softmax_client.http import observatory_client

DEFAULT_API_SERVER = "https://softmax.com/api"
_TRUSTED_HOST_SUFFIXES = (".softmax.com", ".softmax-research.net")
_TRUSTED_EXACT_HOSTS = frozenset({"softmax.com", "localhost", "127.0.0.1", "::1"})


def get_api_server() -> str:
    return os.environ.get("COGAMES_API_URL", DEFAULT_API_SERVER)


class UntrustedApiServerError(Exception):
    """The auth-code exchange destination is outside the trusted hosts."""


ELEVATED_PRIVILEGES_HEADER = "X-Use-Elevated-Privileges"


class WhoAmIResponse(BaseModel):
    user_email: str
    name: str | None = None  # the account's display name, when it has one
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
    browser_path = parsed.path.rstrip("/").removesuffix("/api") + "/cli-auth"
    return urlunsplit((parsed.scheme, parsed.netloc, browser_path, query, ""))


def fetch_cogames_whoami(
    *, api_server: str | None = None, token: str, elevated: bool = False, product: str = "softmax-client"
) -> WhoAmIResponse:
    server = api_server or DEFAULT_API_SERVER
    headers = {ELEVATED_PRIVILEGES_HEADER: "true"} if elevated else {}
    with observatory_client(server=server, token=token, product=product) as client:
        response = client.get("/whoami", headers=headers)
    response.raise_for_status()
    return WhoAmIResponse.model_validate(response.json())


def exchange_auth_code(*, api_server: str, code: str, product: str = "softmax-client") -> str:
    """Exchange a one-time auth code for a real credential token."""
    host = (urlsplit(api_server).hostname or "").lower()
    if host not in _TRUSTED_EXACT_HOSTS and not any(host.endswith(suffix) for suffix in _TRUSTED_HOST_SUFFIXES):
        host = host or api_server
        raise UntrustedApiServerError(
            f"Refusing to send auth code to untrusted host '{host}'. "
            "Auth codes are only exchanged with softmax.com, *.softmax.com, "
            "*.softmax-research.net, or loopback (localhost / 127.0.0.1)."
        )
    response = httpx.post(
        f"{api_server.rstrip('/')}/observatory/credentials/auth-codes/exchange",
        json={"code": code},
        headers={"User-Agent": user_agent(product)},
        timeout=10.0,
    )
    response.raise_for_status()
    return ExchangeSuccess.model_validate(response.json()).token


class ExchangeSuccess(BaseModel):
    token: str


class ExchangeFailure(BaseModel):
    message: str


ExchangeOutcome = ExchangeSuccess | ExchangeFailure


def try_exchange_auth_code(*, api_server: str, code: str, product: str = "softmax-client") -> ExchangeOutcome:
    """Classify expected code-exchange failures for interactive sign-in callers."""
    try:
        token = exchange_auth_code(api_server=api_server, code=code, product=product)
    except UntrustedApiServerError as exc:
        return ExchangeFailure(message=str(exc))
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status // 100 == 3:
            message = (
                "Failed to exchange auth code due to a redirect. "
                "You may have accidentally pointed --server to the frontend application URL.\n"
                "If you have a valid code, you can still run the following command to exchange it for a token:\n\n"
                "softmax exchange-code <code>"
            )
        elif status == 410:
            message = (
                "This auth code has already been used or expired. "
                "If you just ran `softmax login`, your token was saved automatically — "
                "run `softmax status` to verify."
            )
        elif status == 400:
            message = "Invalid auth code format."
        else:
            message = f"Code exchange failed (HTTP {status}): {exc.response.text}"
        return ExchangeFailure(message=message)
    except httpx.HTTPError:
        return ExchangeFailure(
            message=(
                "Could not exchange auth code. Check that --server points at the API "
                "(e.g. https://softmax.com/api) and try again."
            ),
        )
    return ExchangeSuccess(token=token)
