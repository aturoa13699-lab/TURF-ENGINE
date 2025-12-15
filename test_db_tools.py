import json
from pathlib import Path

from engine.turf_engine_pro import overlay_from_stake_card
from tools.db_append import append_cards
from tools.db_init_if_missing import init_db
from tools.backtest import run_backtest
from turf.compile_lite import RunnerInput, compile_stake_card


def build_sample_card(tmp_path: Path) -> Path:
    runner_rows = [
        RunnerInput(1, "One", 1, 3.0, "MID", 17.1),
        RunnerInput(2, "Two", 4, 4.4, "ON_PACE", 17.3),
        RunnerInput(3, "Three", 7, 7.5, "BACK", 17.0),
    ]
    meeting = {"meeting_id": "DEMO", "track_canonical": "RANDWICK", "date_local": "2025-12-13"}
    race = {"race_number": 1, "distance_m": 1200}
    stake_card, _ = compile_stake_card(meeting=meeting, race=race, runner_rows=runner_rows, captured_at="TS")
    runner_vector, forecasts = overlay_from_stake_card(stake_card)
    for runner in stake_card["races"][0]["runners"]:
        rn = runner["runner_number"]
        runner["forecast"] = forecasts[rn]
    stake_path = tmp_path / "stake_card.json"
    stake_path.write_text(json.dumps(stake_card))
    return stake_path


def test_db_init_append_and_backtest(tmp_path: Path):
    db_path = tmp_path / "turf.duckdb"
    conn = init_db(db_path)
    assert (tmp_path).exists()

    stake_dir = tmp_path / "cards"
    stake_dir.mkdir()
    stake_path = build_sample_card(stake_dir)

    inserted = append_cards(db_path, stake_dir)
    assert inserted == 3

    conn.execute(
        "INSERT INTO results VALUES (?, ?, ?, ?, ?)", ("DEMO", 1, 1, 1, 3.0)
    )
    if hasattr(conn, "commit"):
        conn.commit()

    metrics = run_backtest(db_path, model="LOGIT_WIN_PLACE_V0", start=None, end=None, out_dir=tmp_path / "reports")
    assert metrics["count"] > 0
    assert (tmp_path / "reports" / "backtest_metrics.json").exists()
