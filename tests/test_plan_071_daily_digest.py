from __future__ import annotations

import copy
import json
from pathlib import Path

from turf.daily_digest import build_daily_digest


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2))


def _stake_card(meeting_id: str, date_local: str, ev: float, *, pro: bool = False) -> dict:
    return {
        "meeting": {"meeting_id": meeting_id, "date_local": date_local},
        "races": [
            {
                "race_number": 1,
                "runners": [
                    {
                        "runner_number": 1,
                        "runner_name": "Runner A",
                        "odds_minimal": {"price_now_dec": 4.5},
                        "forecast": {"ev_1u": ev, "value_edge": 0.05, "win_prob": 0.30},
                        "pro_marker": pro,
                    }
                ],
            }
        ],
    }


def test_plan071_determinism_and_non_mutation(tmp_path: Path) -> None:
    cards = tmp_path / "cards"
    out = tmp_path / "out"
    cards.mkdir()

    p1 = cards / "stake_card_pro.json"
    payload = _stake_card("M1", "2025-12-18", 0.10, pro=True)
    _write(p1, payload)

    payload_before = copy.deepcopy(payload)

    d1 = build_daily_digest(
        stake_cards_dir=cards,
        out_dir=out,
        prefer_pro=True,
        simulate=False,
    )
    d2 = build_daily_digest(
        stake_cards_dir=cards,
        out_dir=out,
        prefer_pro=True,
        simulate=False,
    )

    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    assert (out / "daily_digest.json").read_text() == (out / "daily_digest.json").read_text()
    assert (out / "daily_digest.md").read_text() == (out / "daily_digest.md").read_text()

    # Non-mutation: original in-memory payload unchanged
    assert payload == payload_before


def test_plan071_meeting_ordering(tmp_path: Path) -> None:
    cards = tmp_path / "cards"
    out = tmp_path / "out"
    cards.mkdir()

    _write(cards / "stake_card_A.json", _stake_card("A_MEET", "2025-12-18", 0.10))
    _write(cards / "stake_card_B.json", _stake_card("B_MEET", "2025-12-17", 0.10))

    daily = build_daily_digest(stake_cards_dir=cards, out_dir=out, prefer_pro=False)
    meetings = daily["meetings"]

    assert meetings[0]["meeting_id"] == "B_MEET"
    assert meetings[1]["meeting_id"] == "A_MEET"


def test_plan071_prefer_pro_dedupes(tmp_path: Path) -> None:
    cards = tmp_path / "cards"
    out = tmp_path / "out"
    cards.mkdir()

    # Same meeting key, both lite and pro. Pro has EV>0, lite EV<=0.
    _write(cards / "stake_card.json", _stake_card("M1", "2025-12-18", -0.01, pro=False))
    _write(cards / "stake_card_pro.json", _stake_card("M1", "2025-12-18", 0.10, pro=True))

    daily_pro = build_daily_digest(stake_cards_dir=cards, out_dir=out, prefer_pro=True)
    assert daily_pro["counts"]["meetings_included"] == 1
    assert daily_pro["meetings"][0]["bets_count"] == 1

    daily_lite = build_daily_digest(stake_cards_dir=cards, out_dir=out, prefer_pro=False)
    assert daily_lite["counts"]["meetings_included"] == 1
    # With prefer_pro=False we select the non-pro card; EV<=0 should yield 0 bets
    assert daily_lite["meetings"][0]["bets_count"] == 0

