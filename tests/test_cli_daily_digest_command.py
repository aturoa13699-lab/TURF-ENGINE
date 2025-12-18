from __future__ import annotations

import re

from typer.testing import CliRunner


def test_cli_has_daily_digest_command() -> None:
    # Import inside the test so failures show up as test failures (not collection errors)
    from cli.turf_cli import app

    runner = CliRunner()
    try:
        result = runner.invoke(app, ["--help"], mix_stderr=True, catch_exceptions=False)
    except TypeError:
        result = runner.invoke(app, ["--help"], catch_exceptions=False)
    combined_output = result.stdout + (result.stderr or "")
    cleaned_output = re.sub(r"\x1b\[[0-9;]*[mK]", "", combined_output)

    assert result.exit_code == 0
    assert "daily-digest" in cleaned_output or "daily digests" in cleaned_output

