import copy
import json

from turf.digest import build_strategy_digest
from turf.simulation import Bet


def test_plan070_digest_deterministic_and_sorted_and_non_mutating():
    stake_card = {
        "meeting": {"meeting_id": "DEMO_MEET", "date_local": "2025-12-18"},
        "races": [{"race_number": 1, "runners": []}],
    }
    stake_orig = copy.deepcopy(stake_card)

    bets = [
        Bet(
            meeting_id="DEMO_MEET",
            date_local="2025-12-18",
            race_number=1,
            runner_number=2,
            odds_dec=4.5,
            win_prob=0.30,
            ev_1u=0.10,
            value_edge=0.05,
        ),
        Bet(
            meeting_id="DEMO_MEET",
            date_local="2025-12-18",
            race_number=1,
            runner_number=1,
            odds_dec=3.0,
            win_prob=0.35,
            ev_1u=0.08,
            value_edge=0.03,
        ),
    ]

    selection_rules = {"require_positive_ev": True, "min_ev": None, "min_edge": None}
    bankroll_policy = {
        "policy": "flat",
        "bankroll_start": 1000.0,
        "flat_stake": 20.0,
        "kelly_fraction": 0.25,
        "max_stake_frac": 0.02,
    }

    d1 = build_strategy_digest(
        stake_card=stake_card,
        bets=bets,
        selection_rules=selection_rules,
        bankroll_policy=bankroll_policy,
        simulation_summary=None,
    )
    d2 = build_strategy_digest(
        stake_card=stake_card,
        bets=bets,
        selection_rules=selection_rules,
        bankroll_policy=bankroll_policy,
        simulation_summary=None,
    )

    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    assert d1["bets"][0]["runner_number"] == 1  # sorted deterministically
    assert stake_card == stake_orig  # non-mutation

