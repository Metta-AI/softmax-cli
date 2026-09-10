import httpx
import pytest

from softmax import rate_limits
from softmax._http import observatory_client


def test_observatory_client_uses_environment_proxy(monkeypatch, httpserver):
    monkeypatch.setenv("HTTP_PROXY", httpserver.url_for(""))
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    httpserver.expect_request("/observatory/whoami", headers={"Authorization": "Bearer token"}).respond_with_json(
        {"proxied": True}
    )

    with observatory_client(server="http://proxy-only.invalid", token="token") as client:
        assert client.get("/whoami").json() == {"proxied": True}


@pytest.mark.parametrize("recover", [False, True])
def test_shared_rejection_retries_preserve_the_request_and_stop(monkeypatch, recover):
    sleeps = []
    monkeypatch.setattr(rate_limits.time, "sleep", sleeps.append)
    monkeypatch.setattr(rate_limits.random, "uniform", lambda *_: 0.125)
    requests = []
    responses = []

    def handle(request):
        requests.append((request.headers["Authorization"], request.content))
        response = httpx.Response(
            200 if recover and len(requests) == 2 else 429,
            headers={"X-RateLimit-Outcome": "rejected", "Retry-After": "1"},
            json={"ok": True},
        )
        responses.append(response)
        return response

    with observatory_client(
        server="https://example.com", token="token", transport=httpx.MockTransport(handle)
    ) as client:
        response = client.post("/submit", json={"idempotency_key": "submission-1"})

    assert response.status_code == (200 if recover else 429)
    assert len(requests) == (2 if recover else 3)
    assert all(request == requests[0] for request in requests)
    assert requests[0][0] == "Bearer token"
    assert sleeps == [1.125] * (len(requests) - 1)
    assert all(response.is_closed for response in responses)


@pytest.mark.parametrize(
    "status,outcome,retry_after",
    [(429, "rejected", "60"), (429, "rejected", "invalid"), (429, "", "1"), (503, "", "1")],
)
def test_unrelated_errors_and_delays_beyond_the_budget_are_not_retried(monkeypatch, status, outcome, retry_after):
    def no_sleep(_seconds):
        pytest.fail("This response must remain actionable without automatic retries")

    monkeypatch.setattr(rate_limits.time, "sleep", no_sleep)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, headers={"X-RateLimit-Outcome": outcome, "Retry-After": retry_after})

    with observatory_client(
        server="https://example.com", token="token", transport=httpx.MockTransport(handle)
    ) as client:
        assert client.get("/resource").status_code == status
    assert len(calls) == 1


def test_retry_budget_does_not_shorten_the_server_delay(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(rate_limits.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(rate_limits.random, "uniform", lambda *_: 0)

    def sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr(rate_limits.time, "sleep", sleep)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(429, headers={"X-RateLimit-Outcome": "rejected", "Retry-After": "20"})

    with observatory_client(
        server="https://example.com", token="token", transport=httpx.MockTransport(handle)
    ) as client:
        assert client.get("/resource").status_code == 429
    assert len(calls) == 2
    assert now[0] == 20


def test_streaming_upload_is_not_retried_after_transport_buffers_it():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(429, headers={"X-RateLimit-Outcome": "rejected", "Retry-After": "0"})

    with observatory_client(
        server="https://example.com", token="token", transport=httpx.MockTransport(handle)
    ) as client:
        response = client.post("/upload", content=iter([b"payload"]))
    assert response.status_code == 429
    assert len(calls) == 1


def test_delayed_wake_preserves_final_response_without_retrying(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(rate_limits.time, "monotonic", lambda: now[0])

    def sleep(_seconds):
        now[0] = 31.0

    monkeypatch.setattr(rate_limits.time, "sleep", sleep)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            429, headers={"X-RateLimit-Outcome": "rejected", "Retry-After": "1"}, json={"retry": "later"}
        )

    with observatory_client(
        server="https://example.com", token="token", transport=httpx.MockTransport(handle)
    ) as client:
        response = client.get("/resource")
    assert response.status_code == 429
    assert response.json() == {"retry": "later"}
    assert len(calls) == 1
