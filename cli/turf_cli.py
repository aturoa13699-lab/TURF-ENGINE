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
from turf.feature_flags import resolve_feature_flags
from turf.race_summary import summarize_race
from turf.value import derive_runner_value_fields
from turf.compile_lite import RunnerInput, compile_stake_card, merge_odds_into_market
from turf.parse_odds import parse_generic_odds_table, parsed_odds_to_market
from turf.parse_ra import parsed_race_to_market_snapshot, parsed_race_to_speed_sidecar, parse_meeting_html
from turf.digest import build_strategy_digest, write_strategy_digest
from turf.simulation import Bet, select_bets_from_stake_card, simulate_bankroll
from turf.daily_digest import build_daily_digest

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


@app.command("digest")
def digest(
    stake_card_path: pathlib.Path = typer.Option(
        ..., "--stake-card", "--stake-card-path", exists=True, help="Path to stake_card_pro.json or stake_card.json"
    ),
    out: pathlib.Path = typer.Option(Path("out/derived"), "--out", help="Output directory for digest artifacts"),
    require_positive_ev: bool = typer.Option(True, help="Require forecast.ev_1u > 0.0"),
    min_ev: Optional[float] = typer.Option(None, help="Minimum forecast.ev_1u (optional)"),
    min_edge: Optional[float] = typer.Option(None, help="Minimum forecast.value_edge (optional)"),
    policy: str = typer.Option("flat", help="Stake policy: flat | kelly | fractional_kelly"),
    bankroll_start: float = typer.Option(1000.0, help="Starting bankroll for stake sizing"),
    flat_stake: float = typer.Option(20.0, help="Flat stake size (policy=flat)"),
    kelly_fraction: float = typer.Option(0.25, help="Kelly fraction (policy=fractional_kelly)"),
    max_stake_frac: float = typer.Option(0.02, help="Max stake fraction of bankroll per bet"),
    simulate: bool = typer.Option(False, help="Run deterministic bankroll simulation and embed summary"),
    iters: int = typer.Option(10000, help="Simulation iterations (if --simulate)"),
    seed: int = typer.Option(1337, help="Simulation RNG seed (if --simulate)"),
):
    """Generate a deterministic strategy digest (JSON + Markdown) from a stake card (derived-only)."""

    payload = json.loads(stake_card_path.read_text())
    bets = select_bets_from_stake_card(
        payload,
        require_positive_ev=require_positive_ev,
        min_ev=min_ev,
        min_edge=min_edge,
    )

    sim_summary = None
    if simulate:
        sim_summary = simulate_bankroll(
            bets=bets,
            iters=iters,
            seed=seed,
            bankroll_start=bankroll_start,
            policy=policy,
            flat_stake=flat_stake,
            kelly_fraction=kelly_fraction,
            max_stake_frac=max_stake_frac,
        )

    digest_payload = build_strategy_digest(
        stake_card=payload,
        bets=bets,
        selection_rules={
            "require_positive_ev": require_positive_ev,
            "min_ev": min_ev,
            "min_edge": min_edge,
        },
        bankroll_policy={
            "policy": policy,
            "bankroll_start": bankroll_start,
            "flat_stake": flat_stake,
            "kelly_fraction": kelly_fraction,
            "max_stake_frac": max_stake_frac,
        },
        simulation_summary=sim_summary,
    )

    write_strategy_digest(out_dir=str(out), digest=digest_payload, filename_base="strategy_digest")
    typer.echo(f"Wrote {out / 'strategy_digest.json'} and {out / 'strategy_digest.md'} (bets={len(bets)})")


@app.command("daily-digest")
def daily_digest(
    stake_cards_dir: pathlib.Path = typer.Option(
        Path("out/cards"), "--stake-cards", "--stake-cards-dir", exists=True, help="Directory containing stake_card*.json files"
    ),
    out: pathlib.Path = typer.Option(Path("out/derived"), "--out", help="Output directory for daily digest artifacts"),
    prefer_pro: bool = typer.Option(True, "--prefer-pro/--no-prefer-pro", help="Prefer *_pro.json for the same meeting when present"),
    require_positive_ev: bool = typer.Option(True, help="Require forecast.ev_1u > 0.0"),
    min_ev: Optional[float] = typer.Option(None, help="Minimum forecast.ev_1u (optional)"),
    min_edge: Optional[float] = typer.Option(None, help="Minimum forecast.value_edge (optional)"),
    policy: str = typer.Option("flat", help="Stake policy: flat | kelly | fractional_kelly"),
    bankroll_start: float = typer.Option(1000.0, help="Starting bankroll for stake sizing"),
    flat_stake: float = typer.Option(20.0, help="Flat stake size (policy=flat)"),
    kelly_fraction: float = typer.Option(0.25, help="Kelly fraction (policy=fractional_kelly)"),
    max_stake_frac: float = typer.Option(0.02, help="Max stake fraction of bankroll per bet"),
    simulate: bool = typer.Option(False, help="Run deterministic bankroll simulation per meeting and embed summary"),
    iters: int = typer.Option(10000, help="Simulation iterations (if --simulate)"),
    seed: int = typer.Option(1337, help="Simulation RNG seed (if --simulate)"),
):
    """Generate a deterministic daily digest from a directory of stake cards (derived-only)."""

    daily = build_daily_digest(
        stake_cards_dir=Path(stake_cards_dir),
        out_dir=Path(out),
        prefer_pro=prefer_pro,
        require_positive_ev=require_positive_ev,
        min_ev=min_ev,
        min_edge=min_edge,
        policy=policy,
        bankroll_start=bankroll_start,
        flat_stake=flat_stake,
        kelly_fraction=kelly_fraction,
        max_stake_frac=max_stake_frac,
        simulate=simulate,
        iters=iters,
        seed=seed,
    )
    typer.echo(f"Wrote {out / 'daily_digest.json'} and {out / 'daily_digest.md'} (meetings={daily.get('counts', {}).get('meetings_included', 0)})")


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


@app.command("preview")
def preview(
    stake_cards: pathlib.Path = typer.Option(
        Path("out/cards"), "--stake-cards", exists=True, help="Directory containing stake card JSON files"
    ),
    out: pathlib.Path = typer.Option(Path("out/previews"), "--out", help="Output directory for HTML/PDF files"),
    format: str = typer.Option("html", "--format", help="Output format: html, pdf, or both"),
    single: Optional[pathlib.Path] = typer.Option(
        None, "--single", help="Render a single stake card file instead of directory"
    ),
    use_pro: bool = typer.Option(
        False, "--use-pro", help="Prefer stake_card_pro.json if available"
    ),
):
    """Generate race preview documents (HTML/PDF) from stake cards.

    This command produces deterministic preview outputs suitable for email
    attachments or printing. PDF generation requires the [pdf] extra:
    pip install turf[pdf]

    PRO fields (EV markers, risk profiles, race summaries) are rendered
    only if present in the input stake card. No derivation is performed.
    """
    from turf.pdf_race_preview import render_previews, render_single_preview

    generate_pdf = format.lower() in ("pdf", "both")

    if single:
        # Single file mode
        if not single.exists():
            typer.echo(f"Error: File not found: {single}", err=True)
            raise typer.Exit(1)

        result = render_single_preview(single, out, generate_pdf=generate_pdf)
        typer.echo(f"HTML: {result['html']}")
        if result.get("pdf"):
            typer.echo(f"PDF: {result['pdf']}")
        elif result.get("pdf_error"):
            typer.echo(f"PDF skipped: {result['pdf_error']}")
    else:
        # Directory mode
        if not stake_cards.is_dir():
            typer.echo(f"Error: Not a directory: {stake_cards}", err=True)
            raise typer.Exit(1)

        results = render_previews(stake_cards, out, generate_pdf=generate_pdf)

        if not results:
            typer.echo(f"No stake cards found in {stake_cards}")
            raise typer.Exit(1)

        typer.echo(f"Rendered {len(results)} preview(s) to {out}")
        for r in results:
            pdf_info = r.get("pdf", r.get("pdf_error", "skipped"))
            typer.echo(f"  - {r['meeting_id']}: HTML={r['html']}, PDF={pdf_info}")


if __name__ == "__main__":
    app()
