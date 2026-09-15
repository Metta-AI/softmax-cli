from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from softmax._http import observatory_client
from softmax.agent import AGENT_ENV_MARKERS, detect_coding_agent, user_agent
from softmax.cli import app

ALL_MARKERS = [variable for _name, variable in AGENT_ENV_MARKERS]


@pytest.fixture(autouse=True)
def _no_ambient_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    # The test process may itself run under a coding agent; start from a clean slate.
    for variable in ALL_MARKERS:
        monkeypatch.delenv(variable, raising=False)


def test_no_marker_means_no_agent() -> None:
    assert detect_coding_agent({}) is None
    assert detect_coding_agent({"CLAUDECODE": ""}) is None


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"CLAUDECODE": "1"}, "claude-code"),
        ({"CLAUDE_CODE_ENTRYPOINT": "cli"}, "claude-code"),
        ({"CODEX_THREAD_ID": "thr_1"}, "codex"),
        ({"CURSOR_AGENT": "1"}, "cursor"),
        ({"GEMINI_CLI": "1"}, "gemini-cli"),
        ({"AI_AGENT": "amp"}, "agent"),
        ({"CURSOR_AGENT": "1", "CLAUDECODE": "1"}, "claude-code"),
    ],
)
def test_markers_identify_the_agent(environ: dict[str, str], expected: str) -> None:
    assert detect_coding_agent(environ) == expected


def test_user_agent_names_the_cli_version_and_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    plain = user_agent("softmax-cli")
    assert plain.startswith("softmax-cli/")
    assert "(" not in plain
    monkeypatch.setenv("CLAUDECODE", "1")
    assert user_agent("softmax-cli") == f"{plain} (claude-code)"
    # No distribution metadata (Bazel and other source-tree runs): still a valid header.
    assert user_agent("no-such-distribution") == "no-such-distribution/dev (claude-code)"


def test_observatory_client_sends_the_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, json={})

    with observatory_client(server="https://example.com", token="token", transport=httpx.MockTransport(handle)) as c:
        c.get("/whoami")
    assert len(seen) == 1
    assert seen[0].startswith("softmax-cli/")
    assert seen[0].endswith("(codex)")


def test_usage_error_prints_full_help_to_stderr_only_under_an_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    human = CliRunner(mix_stderr=False).invoke(app, ["forum", "list"], env={"COLUMNS": "200"})
    assert human.exit_code == 2
    assert "Missing argument" in human.stderr
    assert "--sort" not in human.stderr
    assert human.stdout == ""

    monkeypatch.setenv("CLAUDECODE", "1")
    agent = CliRunner(mix_stderr=False).invoke(app, ["forum", "list"], env={"COLUMNS": "200"})
    assert agent.exit_code == 2
    assert "Missing argument" in agent.stderr
    assert "--sort" in agent.stderr
    assert agent.stdout == ""

    root = CliRunner(mix_stderr=False).invoke(app, ["--bogus"], env={"COLUMNS": "200"})
    assert root.exit_code == 2
    assert "No such option" in root.stderr
    assert "Commands" in root.stderr
    assert root.stdout == ""
