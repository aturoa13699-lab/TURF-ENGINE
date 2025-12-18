from turf.runner_insights import derive_runner_insights, derive_trap_race


def test_gating_all_false():
    runner = {"runner_name": "X"}
    out = derive_runner_insights(runner, enable_summary=False, enable_fitness=False, enable_risk=False)
    assert out == {}


def test_determinism_same_input_same_output():
    runner = {
        "runner_name": "Alpha",
        "barrier": 12,
        "days_since_run": 70,
        "avg_speed_mps": 13.8,
        "map_role_inferred": "BACK",
        "odds_minimal": {"price_now_dec": 18.0},
        "forecast": {"win_prob": 0.12, "market_prob": 0.05, "certainty": 0.9, "value_edge": 0.07},
    }
    a = derive_runner_insights(runner, enable_summary=True, enable_fitness=True, enable_risk=True)
    b = derive_runner_insights(runner, enable_summary=True, enable_fitness=True, enable_risk=True)
    assert a == b
    assert isinstance(a.get("risk_tags"), list)
    assert a["risk_tags"] == b["risk_tags"]


def test_missing_data_safe():
    runner = {}
    out = derive_runner_insights(runner, enable_summary=True, enable_fitness=True, enable_risk=True)
    assert isinstance(out, dict)


def test_trap_race_conservative():
    race = {
        "runners": [
            {"map_role_inferred": "BACK", "barrier": 1, "odds_minimal": {"price_now_dec": 3.2}},
            {"map_role_inferred": "BACK", "barrier": 12, "odds_minimal": {"price_now_dec": None}},
            {"map_role_inferred": "BACK", "barrier": 11, "odds_minimal": {"price_now_dec": None}},
            {"map_role_inferred": "BACK", "barrier": 2, "odds_minimal": {"price_now_dec": None}},
            {"map_role_inferred": "MID", "barrier": 10, "odds_minimal": {"price_now_dec": 9.0}},
            {"map_role_inferred": "LEAD", "barrier": 9, "odds_minimal": {"price_now_dec": 8.0}},
            {"map_role_inferred": "MID", "barrier": 8, "odds_minimal": {"price_now_dec": 10.0}},
            {"map_role_inferred": "MID", "barrier": 7, "odds_minimal": {"price_now_dec": 12.0}},
            {"map_role_inferred": "MID", "barrier": 6, "odds_minimal": {"price_now_dec": 13.0}},
            {"map_role_inferred": "MID", "barrier": 5, "odds_minimal": {"price_now_dec": 14.0}},
            {"map_role_inferred": "MID", "barrier": 4, "odds_minimal": {"price_now_dec": 15.0}},
            {"map_role_inferred": "MID", "barrier": 3, "odds_minimal": {"price_now_dec": 16.0}},
        ]
    }
    assert derive_trap_race(race, {}) is True

