import httpx
import pytest
from typer.testing import CliRunner

from softmax.cli import app


@pytest.mark.parametrize(
    ("args", "url"),
    [
        ([], "https://docs.softmax.com/llms.txt"),
        (["--skill"], "https://docs.softmax.com/skill.md"),
        (["guides/authentication"], "https://docs.softmax.com/guides/authentication.md"),
        (["guides/authentication.md"], "https://docs.softmax.com/guides/authentication.md"),
    ],
)
def test_docs_fetches_raw_text_without_auth(monkeypatch, args, url):
    def get(actual_url, **kwargs):
        assert actual_url == url
        assert kwargs["timeout"] == 30
        assert kwargs["follow_redirects"] is True
        assert set(kwargs["headers"]) == {"User-Agent"}
        assert kwargs["headers"]["User-Agent"].startswith("softmax-cli/")
        return httpx.Response(200, text="# Reference\n", request=httpx.Request("GET", url))

    monkeypatch.setattr("softmax.docs_cli.httpx.get", get)
    result = CliRunner().invoke(app, ["docs", *args])
    assert result.exit_code == 0, result.output
    assert result.output == "# Reference\n"


@pytest.mark.parametrize(
    "args",
    [
        ["../secret"],
        ["https://example.com"],
        ["/absolute"],
        ["a?b"],
        ["a#b"],
        ["%2e%2e/secret"],
        ["a\\b"],
        ["a.md.md"],
        ["page", "--skill"],
    ],
)
def test_docs_rejects_invalid_input_before_network(monkeypatch, args):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid input reached the network")

    monkeypatch.setattr("softmax.docs_cli.httpx.get", unexpected)
    result = CliRunner().invoke(app, ["docs", *args])
    assert result.exit_code == 2


@pytest.mark.parametrize("content_type", ["text/html; charset=utf-8", "application/xhtml+xml"])
def test_docs_rejects_redirected_html(monkeypatch, content_type):
    monkeypatch.setattr(
        "softmax.docs_cli.httpx.get",
        lambda *a, **k: httpx.Response(
            200,
            headers={"Content-Type": content_type},
            text="<html>login</html>",
            request=httpx.Request("GET", "https://docs.softmax.com/login"),
        ),
    )
    result = CliRunner(mix_stderr=False).invoke(app, ["docs"])
    assert result.exit_code == 1
    assert "received HTML" in result.stderr
    assert result.stdout == ""
    assert "Usage:" not in result.output
    assert "<html>" not in result.output


def test_docs_http_failure_uses_existing_error_renderer(monkeypatch):
    monkeypatch.setattr(
        "softmax.docs_cli.httpx.get",
        lambda *a, **k: httpx.Response(
            404, json={"detail": "Missing page"}, request=httpx.Request("GET", "https://docs.softmax.com/missing.md")
        ),
    )
    result = CliRunner().invoke(app, ["docs", "missing"])
    assert result.exit_code == 1
    assert "404" in result.output
    assert "Missing page" in result.output
