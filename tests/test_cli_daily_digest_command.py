from __future__ import annotations

import re
from typer.testing import CliRunner


def test_cli_has_daily_digest_command() -> None:
    # Import inside the test so failures show up as test failures (not collection errors)
    from cli.turf_cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"], color=False)
    assert result.exit_code == 0
    out = (result.stdout or "") + (getattr(result, "stderr", "") or "")
    out = re.sub(r"\x1b\[[0-9;]*m", "", out)
    assert "daily-digest" in out

