"""Smoke tests — prove the package imports and the CLI runs. Expanded per-issue."""
from typer.testing import CliRunner

from semantic_guardian import __version__
from semantic_guardian.cli import app

runner = CliRunner()


def test_version_string_present():
    assert __version__


def test_cli_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
