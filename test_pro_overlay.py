import json
from pathlib import Path

from engine.turf_engine_pro import (
    apply_pro_overlay_to_stake_card,
    build_runner_vector,
    overlay_from_stake_card,
    pro_overlay_logit_win_place_v0,
)
from turf.compile_lite import RunnerInput, compile_stake_card


def test_runner_vector_and_overlay_sum_to_one(tmp_path: Path):
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

    win_sum = sum(v["win_prob"] for v in forecasts.values())
    assert abs(win_sum - 1.0) < 1e-6
    for v in forecasts.values():
        assert 0.0 <= v["place_prob"] <= 1.0

    updated = apply_pro_overlay_to_stake_card(stake_card, runner_vector, forecasts)
    assert updated["engine_context"]["debug"]["runner_vector_checksum"] is not None
    assert all(r.get("forecast") for r in updated["races"][0]["runners"])


def test_overlay_from_stake_card_defaults(tmp_path: Path):
    runner_rows = [
        RunnerInput(1, "Solo", None, None, None, None),
        RunnerInput(2, "Pair", None, None, None, None),
        RunnerInput(3, "Trio", None, None, None, None),
    ]
    meeting = {"meeting_id": "DEMO2", "track_canonical": "RANDWICK", "date_local": "2025-12-14"}
    race = {"race_number": 1, "distance_m": 1400}
    stake_card, _ = compile_stake_card(meeting=meeting, race=race, runner_rows=runner_rows, captured_at="TS", include_overlay=False)

    runner_vector, forecasts = overlay_from_stake_card(stake_card)
    assert runner_vector["debug"]["checksum"]
    assert len(forecasts) == 3
    assert all(0.0 <= v["win_prob"] <= 1.0 for v in forecasts.values())

    applied = apply_pro_overlay_to_stake_card(stake_card, runner_vector, forecasts)
    assert applied["engine_context"]["forecast_params"]["tau"] == 0.12
