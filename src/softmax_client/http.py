"""Shared HTTP client construction for Observatory endpoints."""

from __future__ import annotations

import httpx

from softmax_client.agent import user_agent
from softmax_client.rate_limits import RateLimitTransport


def observatory_client(
    *,
    server: str,
    token: str,
    base: str = "/observatory",
    transport: httpx.BaseTransport | None = None,
    timeout: float = 10.0,
    product: str = "softmax-cli",
) -> httpx.Client:
    """Construct an authenticated client with bounded rate-limit retries; the caller owns closing it."""
    return httpx.Client(
        base_url=f"{server.rstrip('/')}{base}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": user_agent(product)},
        timeout=timeout,
        follow_redirects=True,
        transport=RateLimitTransport(transport),
    )
