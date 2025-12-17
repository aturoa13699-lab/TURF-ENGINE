import json
from pathlib import Path

from typer.testing import CliRunner

from cli.turf_cli import app
from engine.turf_engine_pro import apply_pro_overlay_to_stake_card, build_runner_vector, pro_overlay_logit_win_place_v0
from turf.compile_lite import RunnerInput, compile_stake_card

runner_cli = CliRunner()


def _build_sample_card():
    runner_rows = [
        RunnerInput(1, "One", 1, 3.0, "MID", 17.1),
        RunnerInput(2, "Two", 4, 4.4, "ON_PACE", 17.3),
        RunnerInput(3, "Three", 7, 7.5, "BACK", 17.0),
    ]
    meeting = {"meeting_id": "DEMO", "track_canonical": "RANDWICK", "date_local": "2025-12-13", "track_condition_raw": "Soft 5"}
    race = {"race_number": 1, "distance_m": 1200}
    stake_card, outputs = compile_stake_card(meeting=meeting, race=race, runner_rows=runner_rows, captured_at="TS")
    lite_scores = {o.runner_number: o.lite_score for o in outputs}
    engine_inputs = {
        "distance_m": race["distance_m"],
        "track_condition_raw": meeting["track_condition_raw"],
        "runners": [
            {
                "runner_number": o.runner_number,
                "lite_score": o.lite_score,
                "price_now_dec": runner_rows[i].price_now_dec,
                "barrier": runner_rows[i].barrier,
                "map_role_inferred": runner_rows[i].map_role_inferred,
                "avg_speed_mps": runner_rows[i].avg_speed_mps,
            }
            for i, o in enumerate(outputs)
        ],
    }
    runner_vector = build_runner_vector(engine_inputs)
    prices = {r.runner_number: r.price_now_dec for r in runner_rows}
    forecasts = pro_overlay_logit_win_place_v0(
        runner_vector.get("runners", []),
        prices,
        stake_card.get("engine_context", {}).get("degrade_mode", "NORMAL"),
        stake_card.get("engine_context", {}).get("warnings", []),
    )
    return stake_card, runner_vector, forecasts


def test_value_fields_flagged_on(tmp_path: Path):
    stake_card, runner_vector, forecasts = _build_sample_card()
    updated = apply_pro_overlay_to_stake_card(
        stake_card,
        runner_vector,
        forecasts,
        feature_flags={"ev_bands": True, "race_summary": True},
    )
    runner = updated["races"][0]["runners"][0]
    assert "ev_band" in runner and runner["ev_marker"] is not None
    assert updated["races"][0].get("race_summary")


def test_value_fields_default_off(tmp_path: Path):
    stake_card, runner_vector, forecasts = _build_sample_card()
    updated = apply_pro_overlay_to_stake_card(stake_card, runner_vector, forecasts)
    runner = updated["races"][0]["runners"][0]
    assert "ev_band" not in runner
    assert updated["races"][0].get("race_summary") is None


def test_cli_filter_value(tmp_path: Path):
    stake_card, runner_vector, forecasts = _build_sample_card()
    updated = apply_pro_overlay_to_stake_card(
        stake_card,
        runner_vector,
        forecasts,
        feature_flags={"ev_bands": True, "race_summary": True},
    )
    stake_path = tmp_path / "stake_card_pro.json"
    stake_path.write_text(json.dumps(updated))
    out_path = tmp_path / "filtered.json"
    result = runner_cli.invoke(
        app,
        [
            "filter-value",
            "--stake-card",
            str(stake_path),
            "--min-ev",
            "0.0",
            "--max-price",
            "10",
            "--out",
            str(out_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(out_path.read_text())
    assert payload["runners"]


def test_cli_view_stake_card(tmp_path: Path):
    stake_card, runner_vector, forecasts = _build_sample_card()
    updated = apply_pro_overlay_to_stake_card(
        stake_card,
        runner_vector,
        forecasts,
        feature_flags={"ev_bands": True, "race_summary": True},
    )
    stake_path = tmp_path / "stake_card_pro.json"
    stake_path.write_text(json.dumps(updated))
    result = runner_cli.invoke(app, ["view", "stake-card", "--stake-card", str(stake_path), "--format", "mobile"])
    assert result.exit_code == 0, result.stdout
    assert "Race summary" in result.stdout
    assert "Value picks" in result.stdout
