from __future__ import annotations

import json
import pathlib
import uuid
from typing import List, Optional

import typer
from rich import print

from .compile_lite import RunnerInput, compile_stake_card, merge_odds_into_market
from .models import ExecutionRequest, ExecutionScope, ScrapePlan, ScrapePlanScope, TrackRegistry
from .parse_odds import parse_generic_odds_table, parsed_odds_to_market
from .parse_ra import parsed_race_to_market_snapshot, parsed_race_to_speed_sidecar, parse_meeting_html
from .resolver import build_track_resolver_index, resolve_track, resolve_tracks

app = typer.Typer(help="TURF registry + resolver + scrape plan CLI")
ra_app = typer.Typer(help="Fetch and parse Racing Australia style HTML")
odds_app = typer.Typer(help="Fetch and parse odds HTML")
compile_app = typer.Typer(help="Lite compiler helpers")

app.add_typer(ra_app, name="ra")
app.add_typer(odds_app, name="odds")
app.add_typer(compile_app, name="compile")


@app.command()
def resolve(
    registry: str = typer.Option(..., help="Path to turf.track_registry.v1 JSON"),
    tracks: List[str] = typer.Option(..., help="Track strings to resolve"),
    state_hint: Optional[str] = typer.Option(None, help="Optional state hint (e.g., NSW)"),
):
    with open(registry, "r") as f:
        reg = TrackRegistry.model_validate_json(f.read())
    resolved = resolve_tracks(tracks, reg, state_hint=state_hint)
    print(json.dumps([r.model_dump() for r in resolved], indent=2))


@app.command()
def plan(
    registry: str = typer.Option(..., help="Path to turf.track_registry.v1 JSON"),
    date: str = typer.Option(..., help="YYYY-MM-DD"),
    states: List[str] = typer.Option(..., help="States, e.g., --states NSW --states VIC"),
    tracks: List[str] = typer.Option(..., help="Tracks to include in scope"),
    created_at_local: str = typer.Option("2025-12-09T11:00:00+11:00", help="Local timestamp for plan"),
    tz: str = typer.Option("Australia/Sydney", help="Timezone string"),
    track_registry_version: str = typer.Option("turf.track_registry.v1@0.1.0", help="Registry version ref"),
):
    with open(registry, "r") as f:
        reg = TrackRegistry.model_validate_json(f.read())
    req = ExecutionRequest(
        request_id=str(uuid.uuid4()),
        created_at_local=created_at_local,
        scope=ExecutionScope(date=date, states=states, tracks_raw=tracks),
    )
    resolved = resolve_tracks(req.scope.tracks_raw, reg, state_hint=states[0] if len(states) == 1 else None)
    req.scope.tracks_resolved = resolved
    tracks_scope = [{"canonical": r.canonical, "code": r.code, "state": r.state} for r in resolved]

    sp = ScrapePlan(
        plan_id=str(uuid.uuid4()),
        request_ref=req.request_id,
        created_at_local=created_at_local,
        tz=tz,
        track_registry_version=track_registry_version,
        scope=ScrapePlanScope(date=date, states=states, tracks=tracks_scope),
    )
    print(sp.model_dump_json(indent=2))


@ra_app.command("parse")
def ra_parse(
    html: pathlib.Path = typer.Option(..., exists=True, help="Path to RA meeting HTML"),
    meeting_id: str = typer.Option(..., help="Meeting identifier"),
    race_number: int = typer.Option(..., help="Race number to parse"),
    captured_at: str = typer.Option(..., help="ISO8601 capture time"),
    out_market: pathlib.Path = typer.Option(..., "--out-market", help="Where to write market_snapshot JSON"),
    out_speed: pathlib.Path = typer.Option(..., "--out-speed", help="Where to write runner_speed_derived JSON"),
):
    with open(html, "r") as f:
        parsed = parse_meeting_html(f.read(), meeting_id=meeting_id, race_number=race_number, captured_at=captured_at)

    market = parsed_race_to_market_snapshot(parsed)
    speed = parsed_race_to_speed_sidecar(parsed)
    out_market.write_text(json.dumps(market, indent=2))
    out_speed.write_text(json.dumps(speed, indent=2))
    print(f"Wrote market snapshot to {out_market} and speed sidecar to {out_speed}")


@odds_app.command("parse")
def odds_parse(
    html: pathlib.Path = typer.Option(..., exists=True, help="Path to odds HTML"),
    meeting_id: str = typer.Option(..., help="Meeting identifier"),
    race_number: int = typer.Option(..., help="Race number"),
    captured_at: str = typer.Option(..., help="ISO8601 capture time"),
    out_path: pathlib.Path = typer.Option(..., "--out", help="Where to write parsed odds JSON"),
):
    with open(html, "r") as f:
        rows = parse_generic_odds_table(f.read())
    market = parsed_odds_to_market(rows, meeting_id, race_number, captured_at)
    out_path.write_text(json.dumps(market, indent=2))
    print(f"Wrote parsed odds to {out_path}")


@compile_app.command("merge-odds")
def merge_odds(
    market: pathlib.Path = typer.Option(..., exists=True, help="market_snapshot JSON"),
    odds: pathlib.Path = typer.Option(..., exists=True, help="parsed odds JSON"),
    out_path: pathlib.Path = typer.Option(..., "--out", help="Output merged market snapshot"),
):
    merged = merge_odds_into_market(json.loads(market.read_text()), json.loads(odds.read_text()))
    out_path.write_text(json.dumps(merged, indent=2))
    print(f"Merged odds written to {out_path}")


@compile_app.command("stake-card")
def compile_stake_card_cli(
    market: pathlib.Path = typer.Option(..., exists=True, help="market_snapshot JSON"),
    speed: pathlib.Path = typer.Option(..., exists=True, help="runner_speed_derived JSON"),
    out_path: pathlib.Path = typer.Option(..., "--out", help="Where to write turf.stake_card.v1 JSON"),
    include_overlay: bool = typer.Option(True, help="Whether to compute overlay forecast outputs"),
):
    market_json = json.loads(market.read_text())
    speed_json = json.loads(speed.read_text())

    meeting = market_json.get("meeting", {})
    race = market_json.get("race", {})
    joined: List[RunnerInput] = []
    speed_map = {r.get("runner_number"): r for r in speed_json.get("runners", [])}
    for runner in market_json.get("runners", []):
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

    stake_card, _ = compile_stake_card(
        meeting=meeting,
        race=race,
        runner_rows=joined,
        captured_at=market_json.get("provenance", {}).get("captured_at", "UNKNOWN"),
        include_overlay=include_overlay,
    )
    out_path.write_text(json.dumps(stake_card, indent=2))
    print(f"Stake card written to {out_path}")


if __name__ == "__main__":
    app()
