from __future__ import annotations

"""High-level automation CLI for demo runs, overlays, and site rendering."""

import json
import pathlib
from dataclasses import asdict
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
from turf.simulation import (
    select_bets_from_stake_card,
    sha256_file,
    simulate_bankroll,
    write_json,
)
from turf.feature_flags import resolve_feature_flags
from turf.race_summary import summarize_race
from turf.value import derive_runner_value_fields
from turf.compile_lite import RunnerInput, compile_stake_card, merge_odds_into_market
from turf.parse_odds import parse_generic_odds_table, parsed_odds_to_market
from turf.parse_ra import parsed_race_to_market_snapshot, parsed_race_to_speed_sidecar, parse_meeting_html

app = typer.Typer(help="End-to-end TURF demo runner with overlays and site hooks")
view_app = typer.Typer(help="Read-only stake-card viewers")
app.add_typer(view_app, name="view")


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


def _meeting_meta(stake_card: dict) -> tuple[str, str]:
    meeting = stake_card.get("meeting", {}) or {}
    meeting_id = meeting.get("meeting_id") or stake_card.get("meeting_id") or "unknown_meeting"
    date_local = meeting.get("date_local") or stake_card.get("date_local") or "0000-00-00"
    return meeting_id, date_local


def _discover_stake_cards(root: Path, use_pro: bool) -> list[Path]:
    cards: list[Path] = []
    for lite_path in sorted(root.rglob("stake_card.json")):
        pro_path = lite_path.with_name("stake_card_pro.json")
        chosen = pro_path if use_pro and pro_path.exists() else lite_path
        cards.append(chosen)
    if use_pro:
        for pro_path in sorted(root.rglob("stake_card_pro.json")):
            if pro_path not in cards:
                cards.append(pro_path)
    return cards


def _runner_value_fields(runner: dict) -> dict:
    derived = derive_runner_value_fields(runner)
    forecast = runner.get("forecast") or {}
    odds = (runner.get("odds_minimal") or {}).get("price_now_dec")
    return {
        **derived,
        "price": odds,
        "value_edge": forecast.get("value_edge"),
        "win_prob": forecast.get("win_prob"),
        "runner_number": runner.get("runner_number"),
        "runner_name": runner.get("runner_name", ""),
        "lite_score": runner.get("lite_score", 0.0),
        "lite_tag": runner.get("lite_tag", "PASS_LITE"),
    }


def _format_runner_mobile(runner: dict) -> str:
    ev_marker = runner.get("ev_marker") or "·"
    price = runner.get("price")
    price_text = f"@ {price:.2f}" if isinstance(price, (int, float)) else "@ —"
    edge = runner.get("value_edge")
    edge_text = f"{edge:+.1%}" if isinstance(edge, (int, float)) else "—"
    return f"{ev_marker} #{runner.get('runner_number')}: {runner.get('runner_name','')} {price_text} | edge {edge_text}"


def _format_runner_pretty(runner: dict) -> str:
    ev_band = runner.get("ev_band") or "?"
    risk = runner.get("risk_profile") or "?"
    price = runner.get("price")
    price_text = f"{price:.2f}" if isinstance(price, (int, float)) else "—"
    edge = runner.get("value_edge")
    edge_text = f"{edge:+.2%}" if isinstance(edge, (int, float)) else "—"
    ev_val = runner.get("ev")
    ev_text = f"{ev_val:+.2f}" if isinstance(ev_val, (int, float)) else "—"
    return (
        f"#{runner.get('runner_number')} {runner.get('runner_name','')} | price {price_text} | "
        f"edge {edge_text} | ev {ev_text} | band {ev_band} | risk {risk}"
    )


@app.command()
def demo_run(
    out: pathlib.Path = typer.Option(Path("out/cards"), "--out", help="Directory for generated stake cards"),
    date: Optional[str] = typer.Option(None, help="Date stamp for demo meeting (YYYY-MM-DD)"),
    enable_value_fields: bool = typer.Option(False, help="Enable PRO value/race summary derived fields (Plan 020)"),
    enable_race_summary: bool = typer.Option(False, help="Enable race summary block in PRO output"),
    enable_runner_narratives: bool = typer.Option(False, help="Enable runner narratives (Plan 060, PRO-only)"),
    enable_runner_fitness: bool = typer.Option(False, help="Enable runner fitness flags (Plan 060, PRO-only)"),
    enable_runner_risk: bool = typer.Option(False, help="Enable runner risk tags/profile (Plan 060, PRO-only)"),
    enable_trap_race: bool = typer.Option(False, help="Enable race-level trap_race flag (Plan 060, PRO-only)"),
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
    feature_flags = resolve_feature_flags(
        {
            "ev_bands": enable_value_fields or enable_race_summary,
            "race_summary": enable_race_summary,
            "enable_runner_narratives": enable_runner_narratives,
            "enable_runner_fitness": enable_runner_fitness,
            "enable_runner_risk": enable_runner_risk,
            "enable_trap_race": enable_trap_race,
        }
    )
    stake_card_pro = apply_pro_overlay_to_stake_card(
        stake_card,
        runner_vector_payload,
        forecasts,
        feature_flags=feature_flags,
    )

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
    enable_value_fields: bool = typer.Option(False, help="Enable PRO value/race summary derived fields (Plan 020)"),
    enable_race_summary: bool = typer.Option(False, help="Enable race summary block in PRO output"),
    enable_runner_narratives: bool = typer.Option(False, help="Enable runner narratives (Plan 060, PRO-only)"),
    enable_runner_fitness: bool = typer.Option(False, help="Enable runner fitness flags (Plan 060, PRO-only)"),
    enable_runner_risk: bool = typer.Option(False, help="Enable runner risk tags/profile (Plan 060, PRO-only)"),
    enable_trap_race: bool = typer.Option(False, help="Enable race-level trap_race flag (Plan 060, PRO-only)"),
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
    feature_flags = resolve_feature_flags(
        {
            "ev_bands": enable_value_fields or enable_race_summary,
            "race_summary": enable_race_summary,
            "enable_runner_narratives": enable_runner_narratives,
            "enable_runner_fitness": enable_runner_fitness,
            "enable_runner_risk": enable_runner_risk,
            "enable_trap_race": enable_trap_race,
        }
    )
    updated = apply_pro_overlay_to_stake_card(
        stake_card,
        runner_vector_payload,
        forecasts,
        feature_flags=feature_flags,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(updated, indent=2))
    typer.echo(f"Overlay applied and written to {out}")


@app.command("render-site")
def render_site(
    stake_cards: pathlib.Path = typer.Option(Path("out/cards"), exists=True, help="Directory containing stake card JSON files"),
    out: pathlib.Path = typer.Option(Path("public"), help="Output directory for static site"),
    derive_on_render: bool = typer.Option(
        False, help="Optionally derive EV/race summaries during rendering (default: off)"
    ),
):
    """Render static site from stake cards using the bundled renderer."""

    import importlib.util

    spec = importlib.util.spec_from_file_location("build_site", Path("site/build_site.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    module.build_site(stake_cards, out, derive_on_render=derive_on_render)
    typer.echo(f"Site rendered to {out}")


@app.command("bankroll")
def bankroll(
    stake_cards: pathlib.Path = typer.Option(Path("out/cards"), help="Directory containing stake cards"),
    single: Optional[pathlib.Path] = typer.Option(None, help="Optional single stake card file to process"),
    use_pro: bool = typer.Option(True, help="Prefer stake_card_pro.json when available"),
    out: pathlib.Path = typer.Option(Path("out/derived/sim"), help="Output directory for simulation results"),
    seed: int = typer.Option(123, help="RNG seed for determinism"),
    iters: int = typer.Option(1000, help="Simulation iterations"),
    bankroll_start: float = typer.Option(100.0, help="Starting bankroll"),
    policy: str = typer.Option("flat", help="Staking policy: flat|kelly|fractional_kelly"),
    flat_stake: float = typer.Option(1.0, help="Flat stake size (for flat policy)"),
    kelly_fraction: float = typer.Option(0.25, help="Fractional Kelly multiplier"),
    max_stake_frac: float = typer.Option(0.05, help="Cap per bet as fraction of bankroll"),
    min_ev: Optional[float] = typer.Option(None, help="Minimum EV (ev_1u) required"),
    min_edge: Optional[float] = typer.Option(None, help="Minimum value_edge required"),
    require_positive_ev: bool = typer.Option(True, help="Require ev_1u > 0 by default"),
):
    """Run deterministic bankroll simulation from stake cards (PRO/derived-only)."""

    paths: list[Path] = []
    if single:
        target = Path(single)
        if target.is_dir():
            target = target / ("stake_card_pro.json" if use_pro else "stake_card.json")
        if use_pro and target.name == "stake_card.json":
            pro = target.with_name("stake_card_pro.json")
            if pro.exists():
                target = pro
        paths = [target]
    else:
        root = Path(stake_cards)
        if not root.exists():
            raise typer.BadParameter(f"Stake cards directory not found: {root}")
        paths = _discover_stake_cards(root, use_pro=use_pro)

    if not paths:
        raise typer.BadParameter("No stake_card.json files found to simulate.")

    for card_path in paths:
        stake_card = json.loads(card_path.read_text())
        meeting_id, date_local = _meeting_meta(stake_card)
        bets = select_bets_from_stake_card(
            stake_card,
            require_positive_ev=require_positive_ev,
            min_ev=min_ev,
            min_edge=min_edge,
        )
        summary = simulate_bankroll(
            bets=bets,
            iters=iters,
            seed=seed,
            bankroll_start=bankroll_start,
            policy=policy,
            flat_stake=flat_stake,
            kelly_fraction=kelly_fraction,
            max_stake_frac=max_stake_frac,
        )

        base = out / str(date_local) / str(meeting_id) / card_path.stem
        bets_path = base / "bets_selected.json"
        summary_path = base / "bankroll_summary.json"
        config_path = base / "strategy_inputs.json"

        bets_payload = [asdict(b) for b in bets]
        input_sha = sha256_file(card_path)

        summary_with_meta = {
            **summary,
            "input": {
                "path": str(card_path),
                "input_sha256": input_sha,
                "meeting_id": meeting_id,
                "date_local": date_local,
            },
        }

        write_json(bets_path, {"bets": bets_payload, "count": len(bets_payload)})
        write_json(summary_path, summary_with_meta)
        write_json(
            config_path,
            {
                "seed": seed,
                "iters": iters,
                "policy": policy,
                "flat_stake": flat_stake,
                "kelly_fraction": kelly_fraction,
                "max_stake_frac": max_stake_frac,
                "min_ev": min_ev,
                "min_edge": min_edge,
                "require_positive_ev": require_positive_ev,
                "input_sha256": input_sha,
            },
        )

        typer.echo(f"Simulated bankroll for {card_path} -> {summary_path}")


@app.command("filter-value")
def filter_value(
    stake_card_path: pathlib.Path = typer.Option(
        ..., "--stake-card", "--stake-card-path", exists=True, help="Path to stake_card PRO JSON"
    ),
    min_ev: float = typer.Option(0.05, help="Minimum EV (1u) to include"),
    max_price: float = typer.Option(20.0, help="Maximum price to include"),
    out: pathlib.Path = typer.Option(Path("out/derived/value_filter.json"), help="Where to write filtered runner list"),
):
    """Filter runners by EV and price from a stake card (PRO derived)."""

    payload = json.loads(stake_card_path.read_text())
    race = (payload.get("races") or [{}])[0]
    meeting = payload.get("meeting", {})
    filtered = []
    for runner in race.get("runners", []):
        derived = _runner_value_fields(runner)
        ev_val = derived.get("ev")
        price = derived.get("price")
        if ev_val is None or ev_val < min_ev:
            continue
        if isinstance(price, (int, float)) and price > max_price:
            continue
        filtered.append(
            {
                "runner_number": derived.get("runner_number"),
                "runner_name": derived.get("runner_name"),
                "price": price,
                "ev": ev_val,
                "ev_band": derived.get("ev_band"),
                "ev_marker": derived.get("ev_marker"),
                "value_edge": derived.get("value_edge"),
                "risk_profile": derived.get("risk_profile"),
            }
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "meeting": meeting,
                "race_number": race.get("race_number"),
                "filters": {"min_ev": min_ev, "max_price": max_price},
                "runners": filtered,
            },
            indent=2,
        )
    )
    typer.echo(f"Wrote {out} ({len(filtered)} runners)")


@view_app.command("stake-card")
def view_stake_card(
    stake_card_path: pathlib.Path = typer.Option(
        ..., "--stake-card", "--stake-card-path", exists=True, help="Path to stake_card or stake_card_pro JSON"
    ),
    format: str = typer.Option("mobile", help="Output format: mobile or pretty"),
):
    """Render a stake card in a human-friendly, read-only view."""

    payload = json.loads(stake_card_path.read_text())
    race = (payload.get("races") or [{}])[0]
    runners = [_runner_value_fields(r) for r in race.get("runners", [])]
    summary = race.get("race_summary") or summarize_race(race)
    lines = ["### Race summary"]
    lines.append(f"Top picks: {summary.get('top_picks') or []}")
    lines.append(f"Value picks: {summary.get('value_picks') or []}")
    lines.append(f"Fades: {summary.get('fades') or []}")
    lines.append(f"Trap race: {summary.get('trap_race')}")
    lines.append(f"Strategy: {summary.get('strategy')}")
    lines.append("")
    lines.append("### Runners")
    formatter = _format_runner_mobile if format.lower() == "mobile" else _format_runner_pretty
    ordered = sorted(runners, key=lambda r: (-r.get("lite_score", 0.0), r.get("runner_number") or 0))
    lines.extend(formatter(r) for r in ordered)
    typer.echo("\n".join(lines))


if __name__ == "__main__":
    app()
