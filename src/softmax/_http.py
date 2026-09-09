"""Shared HTTP client construction for Observatory endpoints."""

from __future__ import annotations

import httpx


def observatory_client(
    *,
    server: str,
    token: str,
    base: str = "/observatory",
    transport: httpx.BaseTransport | None = None,
    timeout: float = 10.0,
) -> httpx.Client:
    """Authenticated client rooted at `server`'s Observatory API.

    Every softmax-cli surface that keeps an Observatory client builds it here:
    one place for the bearer header, connect retries, and redirect handling.
    `base` picks the API root the caller's request paths hang off; `transport`
    lets tests inject a MockTransport.
    """
    return httpx.Client(
        base_url=f"{server.rstrip('/')}{base}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
        follow_redirects=True,
        transport=transport or httpx.HTTPTransport(retries=2),
    )
