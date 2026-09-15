from __future__ import annotations

import httpx
import pytest

from softmax.docs import DOCS_AUTHENTICATION_URL, DOCS_ERROR_HANDLING_URL, DOCS_RATE_LIMITS_URL
from softmax.http_errors import render_http_status_error


def _raised(response: httpx.Response) -> httpx.HTTPStatusError:
    """The error httpx itself raises, with its default message."""
    with pytest.raises(httpx.HTTPStatusError) as caught:
        response.raise_for_status()
    return caught.value


def _error(status: int, body: object, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://softmax.com/api/observatory/v2/coworlds/cow_missing")
    return _raised(httpx.Response(status, json=body, headers=headers, request=request))


def test_401_points_at_login_and_the_authentication_docs() -> None:
    message = render_http_status_error(_error(401, {"detail": "Failed to authenticate"}, {"X-Request-Id": "req-1"}))
    assert "GET /api/observatory/v2/coworlds/cow_missing returned HTTP 401" in message
    assert "Detail: Failed to authenticate" in message
    assert "uv run softmax login" in message
    assert "Request id: req-1" in message
    assert f"Docs: {DOCS_AUTHENTICATION_URL}" in message


def test_429_relays_the_servers_documentation_url_and_retry_after() -> None:
    body = {
        "detail": {
            "type": "api_rate_limit_exceeded",
            "message": "API rate limit exceeded.",
            "retry_after_seconds": 7,
            "documentation_url": DOCS_RATE_LIMITS_URL,
        }
    }
    message = render_http_status_error(_error(429, body, {"Retry-After": "7"}))
    assert "Type: api_rate_limit_exceeded" in message
    assert "wait at least 7s" in message
    assert message.count("Docs:") == 1
    assert f"Docs: {DOCS_RATE_LIMITS_URL}" in message


def test_422_without_json_detail_falls_back_to_the_error_handling_page() -> None:
    request = httpx.Request("POST", "https://softmax.com/api/observatory/v2/experience-requests")
    message = render_http_status_error(_raised(httpx.Response(422, text="Unprocessable Entity", request=request)))
    assert "Detail: Unprocessable Entity" in message
    assert "Do not retry unchanged input" in message
    assert f"Docs: {DOCS_ERROR_HANDLING_URL}" in message


def test_a_client_crafted_message_is_kept_and_still_gets_next_step_and_docs() -> None:
    request = httpx.Request("GET", "https://softmax.com/api/observatory/v2/leagues/league_1")
    response = httpx.Response(403, json={"detail": "not yours"}, request=request)
    crafted = httpx.HTTPStatusError(
        "Access denied (403): not yours\nSoftmax team members can request team access by rerunning as "
        "`coworld --elevated <command> ...`.",
        request=request,
        response=response,
    )
    message = render_http_status_error(crafted)
    assert message.startswith("Access denied (403): not yours\n")
    assert "coworld --elevated" in message
    assert "Request failed:" not in message
    assert "Next:" in message
    assert f"Docs: {DOCS_AUTHENTICATION_URL}" in message
