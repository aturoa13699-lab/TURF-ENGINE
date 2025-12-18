from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from turf.daily_digest import build_daily_digest


def _write_stake_card(path: Path, *, meeting_id: str, date_local: str) -> None:
    payload = {
        "meeting": {"meeting_id": meeting_id, "date_local": date_local},
        "races": [
            {
                "race_number": 1,
                "runners": [
                    {
                        "runner_number": 1,
                        "runner_name": "Runner A",
                        "odds_minimal": {"price_now_dec": 4.5},
                        "forecast": {
                            "ev_1u": 0.10,
                            "value_edge": 0.05,
                            "win_prob": 0.30,
                        },
                    }
                ],
            }
        ],
    }
    path.write_text(json.dumps(payload, indent=2))


def test_plan072_default_off_does_not_write_meeting_tree(tmp_path: Path) -> None:
    stake_dir = tmp_path / "cards"
    out_dir = tmp_path / "out"
    stake_dir.mkdir(parents=True, exist_ok=True)

    _write_stake_card(stake_dir / "stake_card_pro.json", meeting_id="MEET_A", date_local="2025-12-18")

    daily = build_daily_digest(
        stake_cards_dir=stake_dir,
        out_dir=out_dir,
        prefer_pro=True,
        write_per_meeting=False,
    )

    assert (out_dir / "daily_digest.json").exists()
    assert (out_dir / "daily_digest.md").exists()
    assert not (out_dir / "meetings").exists()

    m0 = (daily.get("meetings") or [])[0]
    assert "digest_json_path" not in m0
    assert "digest_md_path" not in m0


def test_plan072_write_per_meeting_creates_files_and_indexes(tmp_path: Path) -> None:
    stake_dir = tmp_path / "cards"
    out_dir = tmp_path / "out"
    stake_dir.mkdir(parents=True, exist_ok=True)

    _write_stake_card(stake_dir / "stake_card_meet_a_pro.json", meeting_id="MEET_A", date_local="2025-12-18")
    _write_stake_card(stake_dir / "stake_card_meet_b_pro.json", meeting_id="MEET_B", date_local="2025-12-18")

    daily = build_daily_digest(
        stake_cards_dir=stake_dir,
        out_dir=out_dir,
        prefer_pro=True,
        write_per_meeting=True,
    )

    meetings = daily.get("meetings") or []
    assert len(meetings) == 2
    for m in meetings:
        assert m.get("digest_json_path")
        assert m.get("digest_md_path")
        assert (out_dir / m["digest_json_path"]).exists()
        assert (out_dir / m["digest_md_path"]).exists()

    md = (out_dir / "daily_digest.md").read_text()
    assert "meeting_digest_md:" in md
    assert "meeting_digest_json:" in md


def test_plan072_deterministic_outputs(tmp_path: Path) -> None:
    stake_dir = tmp_path / "cards"
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    stake_dir.mkdir(parents=True, exist_ok=True)

    _write_stake_card(stake_dir / "stake_card_meet_a_pro.json", meeting_id="MEET_A", date_local="2025-12-18")
    _write_stake_card(stake_dir / "stake_card_meet_b_pro.json", meeting_id="MEET_B", date_local="2025-12-18")

    d1 = build_daily_digest(stake_cards_dir=stake_dir, out_dir=out1, write_per_meeting=True)
    d2 = build_daily_digest(stake_cards_dir=stake_dir, out_dir=out2, write_per_meeting=True)

    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    assert (out1 / "daily_digest.md").read_text() == (out2 / "daily_digest.md").read_text()

    # Per-meeting digest JSON bytes must match too.
    m1 = (d1.get("meetings") or [])[0]
    m2 = (d2.get("meetings") or [])[0]
    assert (out1 / m1["digest_json_path"]).read_bytes() == (out2 / m2["digest_json_path"]).read_bytes()


def test_plan072_input_files_not_mutated(tmp_path: Path) -> None:
    stake_dir = tmp_path / "cards"
    out_dir = tmp_path / "out"
    stake_dir.mkdir(parents=True, exist_ok=True)

    p = stake_dir / "stake_card_pro.json"
    _write_stake_card(p, meeting_id="MEET_A", date_local="2025-12-18")
    before = p.read_text()

    build_daily_digest(stake_cards_dir=stake_dir, out_dir=out_dir, write_per_meeting=True)

    after = p.read_text()
    assert before == after

