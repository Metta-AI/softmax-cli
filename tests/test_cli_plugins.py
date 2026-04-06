from typer.testing import CliRunner

from softmax.cli import app

runner = CliRunner()


def test_softmax_help_lists_cogames_command() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "cogames" in result.stdout


def test_softmax_cogames_help_lists_local_commands() -> None:
    result = runner.invoke(app, ["cogames", "--help"])

    assert result.exit_code == 0
    assert "play" in result.stdout
    assert "train" in result.stdout
    assert "eval" in result.stdout
    assert "bundle" in result.stdout
    assert "tutorial" in result.stdout
