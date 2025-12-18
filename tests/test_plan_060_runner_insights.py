from __future__ import annotations

import json

from engine.turf_engine_pro import apply_pro_overlay_to_stake_card


def _base_stake_card(degrade_mode: str = "NORMAL", warnings=None):
    if warnings is None:
        warnings = []
    return {
        "engine_context": {
            "degrade_mode": degrade_mode,
            "warnings": warnings,
        },
        "races": [
            {
                "race_number": 1,
                "runners": [
                    {
                        "runner_number": 1,
                        "runner_name": "Runner A",
                        "barrier": 1,
                        "map_role_inferred": "LEAD",
                        "odds_minimal": {"price_now_dec": 4.5},
                    }
                ],
            }
        ],
    }


def test_plan060_gating_default_off_adds_nothing():
    stake = _base_stake_card()
    original = json.dumps(stake, sort_keys=True)

    out = apply_pro_overlay_to_stake_card(
        stake,
        runner_vector_payload={},
        forecasts={1: {"win_prob": 0.30, "certainty": 1.00}},
        feature_flags=None,  # defaults OFF
    )

    assert json.dumps(stake, sort_keys=True) == original

    runner = out["races"][0]["runners"][0]
    assert "summary" not in runner
    assert "fitness_flags" not in runner
    assert "risk_tags" not in runner
    assert "risk_profile" not in runner
    assert "trap_race" not in out["races"][0]


def test_plan060_enabled_fields_present_and_deterministic():
    stake = _base_stake_card()
    flags = {
        "enable_runner_narratives": True,
        "enable_runner_fitness": True,
        "enable_runner_risk": True,
        "enable_trap_race": False,
    }

    out1 = apply_pro_overlay_to_stake_card(
        stake,
        runner_vector_payload={},
        forecasts={1: {"win_prob": 0.30, "certainty": 1.00}},
        feature_flags=flags,
    )
    out2 = apply_pro_overlay_to_stake_card(
        stake,
        runner_vector_payload={},
        forecasts={1: {"win_prob": 0.30, "certainty": 1.00}},
        feature_flags=flags,
    )

    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)

    runner = out1["races"][0]["runners"][0]
    assert "summary" in runner
    assert "fitness_flags" in runner and isinstance(runner["fitness_flags"], list)
    assert "risk_tags" in runner and isinstance(runner["risk_tags"], list)
    assert runner.get("risk_profile") == "VALUE"


def test_plan060_trap_race_only_when_flag_enabled():
    stake = _base_stake_card(degrade_mode="PARTIAL_SIDECAR", warnings=["JOIN_MISS"])
    forecasts = {1: {"win_prob": 0.30, "certainty": 0.60}}

    out_off = apply_pro_overlay_to_stake_card(
        stake,
        runner_vector_payload={},
        forecasts=forecasts,
        feature_flags={"enable_trap_race": False},
    )
    assert "trap_race" not in out_off["races"][0]

    out_on = apply_pro_overlay_to_stake_card(
        stake,
        runner_vector_payload={},
        forecasts=forecasts,
        feature_flags={"enable_trap_race": True},
    )
    assert out_on["races"][0].get("trap_race") is True

