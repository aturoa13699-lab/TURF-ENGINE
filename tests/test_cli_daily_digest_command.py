from __future__ import annotations

from typer.testing import CliRunner


def test_cli_has_daily_digest_command() -> None:
    # Import inside the test so failures show up as test failures (not collection errors)
    from cli.turf_cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "daily-digest" in result.stdout

