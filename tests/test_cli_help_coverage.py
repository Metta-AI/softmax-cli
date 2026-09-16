"""Every softmax command must describe itself and the root help must name the docs."""

from __future__ import annotations

import click
from typer.main import get_command
from typer.testing import CliRunner

from softmax.cli import DOCS_AGENT_INDEX_URL, DOCS_AGENT_SKILL_URL, DOCS_FORUMS_AND_WIKIS_URL, app


def _walk(group: click.Group, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], click.Command]]:
    found: list[tuple[tuple[str, ...], click.Command]] = []
    for name, command in group.commands.items():
        path = (*prefix, name)
        found.append((path, command))
        if isinstance(command, click.Group):
            found.extend(_walk(command, path))
    return found


def test_every_softmax_command_has_help_text() -> None:
    root = get_command(app)
    assert isinstance(root, click.Group)
    missing = [" ".join(path) for path, command in _walk(root) if not (command.help or "").strip()]
    assert missing == []


def test_root_and_community_help_name_the_docs() -> None:
    root_help = CliRunner().invoke(app, ["--help"], env={"COLUMNS": "400"}).output
    assert "docs" in root_help
    assert DOCS_AGENT_INDEX_URL in root_help
    assert DOCS_AGENT_SKILL_URL in root_help
    for subapp in ("forum", "wiki"):
        assert DOCS_FORUMS_AND_WIKIS_URL in CliRunner().invoke(app, [subapp, "--help"], env={"COLUMNS": "400"}).output


def test_set_token_prints_next_steps(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["set-token", "usr_test-token"], env={"COLUMNS": "400"})
    assert result.exit_code == 0, result.output
    assert "Token saved" in result.output
    assert "coworld leagues" in result.output
    assert DOCS_AGENT_INDEX_URL in result.output
    assert DOCS_AGENT_SKILL_URL in result.output


def test_next_steps_carry_a_non_default_server(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = CliRunner().invoke(
        app, ["set-token", "usr_test-token", "--server", "http://localhost:3002/api"], env={"COLUMNS": "400"}
    )
    assert result.exit_code == 0, result.output
    assert "softmax status --server http://localhost:3002/api" in result.output
    assert "coworld leagues --server http://localhost:3002/api" in result.output
