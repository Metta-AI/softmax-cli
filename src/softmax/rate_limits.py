"""Bounded retries for Observatory's pre-execution API budget rejections."""

import random
import re
import time

import httpx


class RateLimitTransport(httpx.BaseTransport):
    """Make at most three attempts, starting retries within 30 seconds.

    Only shared-budget rejections guarantee that the endpoint did not execute.
    Other 429s and streaming uploads retain their caller's error handling.
    Each attempt keeps the underlying client's network timeouts.
    """

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(transport=transport)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        deadline = time.monotonic() + 30
        replayable = isinstance(request.stream, httpx.ByteStream)
        attempts = 0
        while True:
            response = self._client.send(request, stream=True, auth=None, follow_redirects=False)
            attempts += 1
            if (
                response.status_code != 429
                or response.headers.get("X-RateLimit-Outcome") != "rejected"
                or not replayable
                or attempts == 3
            ):
                return response

            retry_after = response.headers.get("Retry-After", "")
            if not re.fullmatch(r"[0-9]{1,9}", retry_after):
                return response
            delay = int(retry_after) + random.uniform(0, 0.25)
            if time.monotonic() + delay >= deadline:
                return response
            time.sleep(delay)
            if time.monotonic() >= deadline:
                return response
            response.close()

    def close(self) -> None:
        self._client.close()
