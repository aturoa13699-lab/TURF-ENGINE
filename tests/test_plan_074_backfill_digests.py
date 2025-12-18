from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cli import turf_cli
from turf.backfill_digests import BackfillConfig, backfill_digests


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


def test_plan074_backfill_deterministic_and_non_mutating(tmp_path: Path) -> None:
    stake_root = tmp_path / "stake_cards"
    out_dir = tmp_path / "out"

    stake_root.mkdir()
    originals: dict[Path, bytes] = {}
    dates = ["2025-12-18", "2025-12-19"]
    for idx, d in enumerate(dates):
        day_dir = stake_root / d
        day_dir.mkdir(parents=True, exist_ok=True)
        lite = _stake_card(f"M{idx+1}", d, 0.05)
        pro = _stake_card(f"M{idx+1}", d, 0.10, pro=True)
        lite_path = day_dir / "stake_card.json"
        pro_path = day_dir / "stake_card_pro.json"
        _write(lite_path, lite)
        _write(pro_path, pro)
        originals[lite_path] = lite_path.read_bytes()
        originals[pro_path] = pro_path.read_bytes()

    cfg = BackfillConfig(
        from_date=dates[0],
        to_date=dates[-1],
        days=len(dates),
        out_dir=out_dir,
        stake_cards_dir=stake_root,
        prefer_pro=True,
        simulate=False,
        seed=1337,
        write_per_meeting=True,
        render_html=False,
    )

    first = backfill_digests(cfg)
    index_json_1 = (out_dir / "index.json").read_bytes()
    index_md_1 = (out_dir / "index.md").read_bytes()
    first_daily_json = (out_dir / dates[0] / "derived" / "daily_digest.json").read_bytes()
    first_daily_md = (out_dir / dates[0] / "derived" / "daily_digest.md").read_bytes()

    second = backfill_digests(cfg)
    assert index_json_1 == (out_dir / "index.json").read_bytes()
    assert index_md_1 == (out_dir / "index.md").read_bytes()
    assert first_daily_json == (out_dir / dates[0] / "derived" / "daily_digest.json").read_bytes()
    assert first_daily_md == (out_dir / dates[0] / "derived" / "daily_digest.md").read_bytes()

    assert [d["date"] for d in first["dates"]] == sorted(dates)
    assert [d["date"] for d in second["dates"]] == sorted(dates)

    for d in dates:
        derived_dir = out_dir / d / "derived"
        assert (derived_dir / "daily_digest.json").exists()
        assert (derived_dir / "daily_digest.md").exists()
        meetings_dir = derived_dir / "meetings"
        assert meetings_dir.exists()
        assert any(meetings_dir.glob("*/strategy_digest.json"))
        assert any(meetings_dir.glob("*/strategy_digest.md"))

    for path, original_bytes in originals.items():
        assert path.read_bytes() == original_bytes


def test_plan074_cli_registers_backfill_command() -> None:
    runner = CliRunner()
    result = runner.invoke(turf_cli.app, ["--help"])
    assert result.exit_code == 0
    assert "backfill-digests" in result.stdout
