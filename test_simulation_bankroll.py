from pathlib import Path

import json

from turf.simulation import select_bets_from_stake_card, simulate_bankroll, sha256_file, write_json


def _minimal_card(ev: float | None = 0.1, win_prob: float | None = 0.55, odds: float | None = 2.0):
    return {
        "meeting": {"meeting_id": "MEET1", "date_local": "2025-12-15"},
        "races": [
            {
                "race_number": 1,
                "runners": [
                    {
                        "runner_number": 3,
                        "odds_minimal": {"price_now_dec": odds},
                        "forecast": {"ev_1u": ev, "win_prob": win_prob, "value_edge": 0.12},
                    }
                ],
            }
        ],
    }


def test_simulation_deterministic(tmp_path: Path):
    card_path = tmp_path / "stake_card.json"
    card = _minimal_card()
    card_path.write_text(json.dumps(card))

    bets = select_bets_from_stake_card(card)
    summary_a = simulate_bankroll(
        bets=bets,
        iters=200,
        seed=123,
        bankroll_start=100.0,
        policy="flat",
        flat_stake=1.0,
        kelly_fraction=0.25,
        max_stake_frac=0.05,
    )
    summary_b = simulate_bankroll(
        bets=bets,
        iters=200,
        seed=123,
        bankroll_start=100.0,
        policy="flat",
        flat_stake=1.0,
        kelly_fraction=0.25,
        max_stake_frac=0.05,
    )

    # Write and compare sha to ensure stable output formatting
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    write_json(out_a, summary_a)
    write_json(out_b, summary_b)
    assert sha256_file(out_a) == sha256_file(out_b)


def test_policy_variation_changes_results(tmp_path: Path):
    card = _minimal_card(ev=0.2, win_prob=0.6, odds=2.2)
    bets = select_bets_from_stake_card(card)
    flat = simulate_bankroll(
        bets=bets,
        iters=200,
        seed=7,
        bankroll_start=100.0,
        policy="flat",
        flat_stake=1.0,
        kelly_fraction=0.25,
        max_stake_frac=0.05,
    )
    kelly = simulate_bankroll(
        bets=bets,
        iters=200,
        seed=7,
        bankroll_start=100.0,
        policy="kelly",
        flat_stake=1.0,
        kelly_fraction=0.25,
        max_stake_frac=0.05,
    )

    assert flat["results"]["mean_final"] != kelly["results"]["mean_final"]


def test_no_bets_is_safe(tmp_path: Path):
    card = _minimal_card(ev=None, win_prob=None, odds=None)
    bets = select_bets_from_stake_card(card)
    assert bets == []

    summary = simulate_bankroll(
        bets=bets,
        iters=50,
        seed=99,
        bankroll_start=100.0,
        policy="flat",
        flat_stake=1.0,
        kelly_fraction=0.25,
        max_stake_frac=0.05,
    )

    assert summary["counts"]["bets_considered"] == 0
    assert summary["counts"]["bets_simulated"] == 0
    assert summary["results"]["mean_final"] == 100.0

