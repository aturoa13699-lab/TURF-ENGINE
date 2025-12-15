from __future__ import annotations

"""High-level automation CLI for demo runs, overlays, and site rendering."""

import json
import pathlib
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from engine.turf_engine_pro import (
    apply_pro_overlay_to_stake_card,
    build_runner_vector,
    overlay_from_stake_card,
    pro_overlay_logit_win_place_v0,
)
from turf.compile_lite import RunnerInput, compile_stake_card, merge_odds_into_market
from turf.parse_odds import parse_generic_odds_table, parsed_odds_to_market
from turf.parse_ra import parsed_race_to_market_snapshot, parsed_race_to_speed_sidecar, parse_meeting_html

app = typer.Typer(help="End-to-end TURF demo runner with overlays and site hooks")


def _load_demo_artifacts(date: str) -> tuple[dict, dict, dict]:
    meeting_html = Path("data/demo_meeting.html")
    odds_html = Path("data/demo_odds.html")
    meeting_id = f"DEMO_{date}"
    race_number = 1

    parsed = parse_meeting_html(meeting_html.read_text(), meeting_id=meeting_id, race_number=race_number, captured_at=f"{date}T10:00:00+11:00")
    market = parsed_race_to_market_snapshot(parsed)
    speed = parsed_race_to_speed_sidecar(parsed)

    odds_rows = parse_generic_odds_table(odds_html.read_text())
    odds = parsed_odds_to_market(odds_rows, meeting_id, race_number, f"{date}T10:01:00+11:00")
    return market, speed, odds


def _join_runner_inputs(market: dict, speed: dict) -> list[RunnerInput]:
    joined = []
    speed_map = {r.get("runner_number"): r for r in speed.get("runners", [])}
    for runner in market.get("runners", []):
        sidecar = speed_map.get(runner.get("runner_number"), {})
        joined.append(
            RunnerInput(
                runner_number=runner.get("runner_number"),
                runner_name=runner.get("runner_name"),
                barrier=runner.get("barrier"),
                price_now_dec=(runner.get("odds_minimal") or {}).get("price_now_dec"),
                map_role_inferred=sidecar.get("map_role_inferred"),
                avg_speed_mps=sidecar.get("avg_speed_mps"),
            )
        )
    return joined


def _build_engine_inputs(market: dict, speed: dict, lite_scores: dict) -> dict:
    speed_map = {r.get("runner_number"): r for r in speed.get("runners", [])}
    runners = []
    for runner in market.get("runners", []):
        rn = runner.get("runner_number")
        odds_block = runner.get("odds_minimal") or {}
        sidecar = speed_map.get(rn, {})
        runners.append(
            {
                "runner_number": rn,
                "lite_score": lite_scores.get(rn, 0.5),
                "price_now_dec": odds_block.get("price_now_dec"),
                "barrier": runner.get("barrier"),
                "map_role_inferred": sidecar.get("map_role_inferred"),
                "avg_speed_mps": sidecar.get("avg_speed_mps"),
            }
        )
    return {
        "distance_m": market.get("race", {}).get("distance_m"),
        "track_condition_raw": market.get("race", {}).get("track_condition_raw") or market.get("meeting", {}).get("track_condition_raw"),
        "field_size": len(runners),
        "runners": runners,
    }


@app.command()
def demo_run(
    out: pathlib.Path = typer.Option(Path("out/cards"), "--out", help="Directory for generated stake cards"),
    date: Optional[str] = typer.Option(None, help="Date stamp for demo meeting (YYYY-MM-DD)"),
):
    """Run the full Lite + PRO overlay pipeline using bundled demo fixtures."""

    out.mkdir(parents=True, exist_ok=True)
    run_date = date or datetime.utcnow().date().isoformat()
    market, speed, odds = _load_demo_artifacts(run_date)
    merged_market = merge_odds_into_market(market, odds)

    runner_rows = _join_runner_inputs(merged_market, speed)
    stake_card, runner_outputs = compile_stake_card(
        meeting=merged_market.get("meeting", {}),
        race=merged_market.get("race", {}),
        runner_rows=runner_rows,
        captured_at=merged_market.get("provenance", {}).get("captured_at", "DEMO_TS"),
        include_overlay=True,
    )
    lite_scores = {o.runner_number: o.lite_score for o in runner_outputs}

    engine_inputs = _build_engine_inputs(merged_market, speed, lite_scores)
    runner_vector_payload = build_runner_vector(engine_inputs)
    price_map = {row.get("runner_number"): (row.get("odds_minimal") or {}).get("price_now_dec") for row in merged_market.get("runners", [])}
    forecasts = pro_overlay_logit_win_place_v0(
        runner_vector_payload.get("runners", []),
        price_map,
        stake_card.get("engine_context", {}).get("degrade_mode", "NORMAL"),
        stake_card.get("engine_context", {}).get("warnings", []),
    )
    stake_card_pro = apply_pro_overlay_to_stake_card(stake_card, runner_vector_payload, forecasts)

    lite_path = out / "stake_card.json"
    pro_path = out / "stake_card_pro.json"
    rv_path = out / "runner_vector.json"
    lite_path.write_text(json.dumps(stake_card, indent=2))
    pro_path.write_text(json.dumps(stake_card_pro, indent=2))
    rv_path.write_text(json.dumps(runner_vector_payload, indent=2))
    typer.echo(f"Wrote {lite_path} and {pro_path}")


@app.command("apply-overlay")
def apply_overlay(
    stake_card_path: pathlib.Path = typer.Option(..., exists=True, help="Path to stake_card JSON"),
    out: pathlib.Path = typer.Option(..., help="Where to write overlay-updated stake_card"),
    runner_vector_path: Optional[pathlib.Path] = typer.Option(None, help="Optional precomputed runner_vector JSON"),
):
    """Apply the deterministic PRO overlay to an existing stake card."""

    stake_card = json.loads(stake_card_path.read_text())
    if runner_vector_path:
        runner_vector_payload = json.loads(runner_vector_path.read_text())
    else:
        runner_vector_payload, _ = overlay_from_stake_card(stake_card)

    race = (stake_card.get("races") or [{}])[0]
    prices = {}
    for runner in race.get("runners", []):
        odds_block = runner.get("odds_minimal") or {}
        prices[runner.get("runner_number")] = odds_block.get("price_now_dec")

    forecasts = pro_overlay_logit_win_place_v0(
        runner_vector_payload.get("runners", []),
        prices,
        stake_card.get("engine_context", {}).get("degrade_mode", "NORMAL"),
        stake_card.get("engine_context", {}).get("warnings", []),
    )
    updated = apply_pro_overlay_to_stake_card(stake_card, runner_vector_payload, forecasts)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(updated, indent=2))
    typer.echo(f"Overlay applied and written to {out}")


@app.command("render-site")
def render_site(
    stake_cards: pathlib.Path = typer.Option(Path("out/cards"), exists=True, help="Directory containing stake card JSON files"),
    out: pathlib.Path = typer.Option(Path("public"), help="Output directory for static site"),
):
    """Render static site from stake cards using the bundled renderer."""

    import importlib.util

    spec = importlib.util.spec_from_file_location("build_site", Path("site/build_site.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    module.build_site(stake_cards, out)
    typer.echo(f"Site rendered to {out}")


if __name__ == "__main__":
    app()
