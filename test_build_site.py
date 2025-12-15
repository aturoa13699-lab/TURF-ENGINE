import importlib.util
import importlib.util
import json
from pathlib import Path

from turf.compile_lite import RunnerInput, compile_stake_card


def load_build_site():
    spec = importlib.util.spec_from_file_location("build_site", Path("site/build_site.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_site_outputs_pages(tmp_path: Path):
    runner_rows = [
        RunnerInput(
            runner_number=1,
            runner_name="Runner A",
            barrier=1,
            price_now_dec=3.0,
            map_role_inferred="MID",
            avg_speed_mps=17.1,
        ),
        RunnerInput(
            runner_number=2,
            runner_name="Runner B",
            barrier=5,
            price_now_dec=4.5,
            map_role_inferred="ON_PACE",
            avg_speed_mps=17.5,
        ),
        RunnerInput(
            runner_number=3,
            runner_name="Runner C",
            barrier=7,
            price_now_dec=9.5,
            map_role_inferred="BACK",
            avg_speed_mps=17.0,
        ),
    ]
    meeting = {"meeting_id": "DEMO", "track_canonical": "RANDWICK", "date_local": "2025-12-13"}
    race = {"race_number": 1, "distance_m": 1200}
    stake_card, _ = compile_stake_card(meeting=meeting, race=race, runner_rows=runner_rows, captured_at="DEMO_TS")

    stake_dir = tmp_path / "stake_cards"
    stake_dir.mkdir()
    stake_path = stake_dir / "stake_card.json"
    stake_path.write_text(json.dumps(stake_card))
    payload = json.loads(stake_path.read_text())
    assert payload["races"][0]["runners"][0]["forecast"]["ev_1u"] is not None

    out_dir = tmp_path / "public"
    build_site = load_build_site().build_site
    build_site(stake_dir, out_dir)

    index_html = (out_dir / "index.html").read_text()
    race_html = (out_dir / "races" / "DEMO_R1.html").read_text()

    assert "Runner A" in index_html
    assert "LiteScore" in race_html
    assert "EV" in race_html
    assert (out_dir / "static" / "styles.css").exists()
