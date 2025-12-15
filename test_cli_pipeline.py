import json
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from turf.cli import app

runner = CliRunner()


def test_full_cli_pipeline(tmp_path: Path):
    meeting_html = Path("data/demo_meeting.html")
    odds_html = Path("data/demo_odds.html")

    market_path = tmp_path / "market_snapshot.json"
    speed_path = tmp_path / "runner_speed.json"
    odds_path = tmp_path / "odds.json"
    merged_path = tmp_path / "market_with_odds.json"
    stake_card_path = tmp_path / "stake_card.json"

    result = runner.invoke(
        app,
        [
            "ra",
            "parse",
            "--html",
            str(meeting_html),
            "--meeting-id",
            "DEMO_MEETING",
            "--race-number",
            "1",
            "--captured-at",
            "2025-12-13T10:00:00+11:00",
            "--out-market",
            str(market_path),
            "--out-speed",
            str(speed_path),
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        app,
        [
            "odds",
            "parse",
            "--html",
            str(odds_html),
            "--meeting-id",
            "DEMO_MEETING",
            "--race-number",
            "1",
            "--captured-at",
            "2025-12-13T10:01:00+11:00",
            "--out",
            str(odds_path),
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        app,
        [
            "compile",
            "merge-odds",
            "--market",
            str(market_path),
            "--odds",
            str(odds_path),
            "--out",
            str(merged_path),
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        app,
        [
            "compile",
            "stake-card",
            "--market",
            str(merged_path),
            "--speed",
            str(speed_path),
            "--out",
            str(stake_card_path),
        ],
    )
    assert result.exit_code == 0, result.output

    stake = json.loads(stake_card_path.read_text())
    assert stake["engine_context"]["engine_spec_id"] == "TURF_ENGINE_LITE_AU"
    runners = stake["races"][0]["runners"]
    assert all(r.get("forecast") for r in runners)
    assert any((r.get("odds_minimal") or {}).get("price_now_dec") for r in runners)
    # ordering isolated to runner_number final anchor
    assert [r["runner_number"] for r in runners] == sorted(r["runner_number"] for r in runners)
