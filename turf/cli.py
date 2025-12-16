from __future__ import annotations

import json
import math
import pathlib
import uuid
from typing import List, Optional

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from .compile_lite import RunnerInput, compile_stake_card, merge_odds_into_market
from .models import ExecutionRequest, ExecutionScope, ScrapePlan, ScrapePlanScope, TrackRegistry
from .parse_odds import parse_generic_odds_table, parsed_odds_to_market
from .parse_ra import parsed_race_to_market_snapshot, parsed_race_to_speed_sidecar, parse_meeting_html
from .resolver import build_track_resolver_index, resolve_track, resolve_tracks

app = typer.Typer(help="TURF registry + resolver + scrape plan CLI")
ra_app = typer.Typer(help="Fetch and parse Racing Australia style HTML")
odds_app = typer.Typer(help="Fetch and parse odds HTML")
compile_app = typer.Typer(help="Lite compiler helpers")
filter_app = typer.Typer(help="Filter and analyze stake cards")
matchups_app = typer.Typer(help="Head-to-head matchup analysis")

app.add_typer(ra_app, name="ra")
app.add_typer(odds_app, name="odds")
app.add_typer(compile_app, name="compile")
app.add_typer(filter_app, name="filter")
app.add_typer(matchups_app, name="matchups")


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


# ============================================================================
# Value Bet Filter
# ============================================================================

def calculate_ev(probability: float, odds: float) -> float:
    """Calculate expected value per $1 stake.

    EV = p * (O - 1) - (1 - p) * 1 = p * O - 1

    Args:
        probability: Win probability (0-1)
        odds: Decimal odds (e.g., 3.50)

    Returns:
        Expected value per $1 stake
    """
    if probability <= 0 or odds <= 1:
        return float("-inf")
    return probability * odds - 1


@filter_app.command("value")
def filter_value(
    stake_card: pathlib.Path = typer.Option(..., "--stake-card", exists=True, help="Path to stake_card JSON"),
    min_ev: float = typer.Option(0.05, "--min-ev", help="Minimum EV threshold (e.g., 0.05 = 5%)"),
    max_price: Optional[float] = typer.Option(None, "--max-price", help="Maximum price filter (e.g., 10.0)"),
    min_price: Optional[float] = typer.Option(None, "--min-price", help="Minimum price filter (e.g., 2.0)"),
    out_path: Optional[pathlib.Path] = typer.Option(None, "--out", help="Output JSON file (optional)"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress table output"),
):
    """Filter runners by expected value and price range.

    EV Formula: EV = p * O - 1 (where p = win probability, O = decimal odds)

    Positive EV indicates a profitable bet in expectation.
    """
    card = json.loads(stake_card.read_text())
    races = card.get("races", [])
    meeting = card.get("meeting", {})

    value_bets = []

    for race in races:
        race_number = race.get("race_number")
        for runner in race.get("runners", []):
            forecast = runner.get("forecast") or {}
            odds_block = runner.get("odds_minimal") or {}

            win_prob = forecast.get("win_prob")
            price = odds_block.get("price_now_dec")

            # Skip if missing required data
            if win_prob is None or price is None:
                continue

            # Apply price filters
            if max_price is not None and price > max_price:
                continue
            if min_price is not None and price < min_price:
                continue

            # Calculate EV
            ev = calculate_ev(win_prob, price)

            # Apply EV filter
            if ev < min_ev:
                continue

            value_bets.append({
                "meeting_id": meeting.get("meeting_id"),
                "race_number": race_number,
                "runner_number": runner.get("runner_number"),
                "runner_name": runner.get("runner_name"),
                "lite_tag": runner.get("lite_tag"),
                "price": price,
                "win_prob": win_prob,
                "ev": ev,
                "ev_pct": ev * 100,
            })

    # Sort by EV descending, then runner_number ascending for stability
    value_bets.sort(key=lambda x: (-x["ev"], x.get("runner_number", 0)))

    # Output table
    if not quiet and value_bets:
        console = Console()
        table = Table(title=f"Value Bets (EV ≥ {min_ev*100:.1f}%)")
        table.add_column("Race", style="cyan")
        table.add_column("Runner", style="magenta")
        table.add_column("Name")
        table.add_column("Tag", style="yellow")
        table.add_column("Price", justify="right")
        table.add_column("Win%", justify="right")
        table.add_column("EV%", justify="right", style="green")

        for bet in value_bets:
            table.add_row(
                str(bet["race_number"]),
                str(bet["runner_number"]),
                bet["runner_name"][:20],
                bet["lite_tag"] or "—",
                f"{bet['price']:.2f}",
                f"{bet['win_prob']*100:.1f}%",
                f"{bet['ev_pct']:+.1f}%",
            )

        console.print(table)
        print(f"\n[bold]Found {len(value_bets)} value bet(s)[/bold]")
    elif not quiet:
        print("[yellow]No value bets found matching criteria[/yellow]")

    # Output JSON
    if out_path:
        output = {
            "filter_params": {
                "min_ev": min_ev,
                "max_price": max_price,
                "min_price": min_price,
            },
            "meeting_id": meeting.get("meeting_id"),
            "count": len(value_bets),
            "bets": value_bets,
        }
        out_path.write_text(json.dumps(output, indent=2))
        print(f"Value bets written to {out_path}")

    return value_bets


# ============================================================================
# Head-to-Head Matchups
# ============================================================================

def sigmoid(x: float) -> float:
    """Numerically stable sigmoid function."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        exp_x = math.exp(x)
        return exp_x / (1.0 + exp_x)


def logit(p: float, eps: float = 1e-10) -> float:
    """Logit function with numerical stability."""
    p = max(eps, min(1 - eps, p))
    return math.log(p / (1 - p))


def calculate_pairwise_probability(prob_i: float, prob_j: float) -> float:
    """Calculate P(i beats j) using Bradley-Terry style model.

    Uses logit scores: score_i = logit(p_i)
    P(i beats j) = sigmoid(score_i - score_j)

    This ensures symmetry: P(i beats j) + P(j beats i) = 1
    """
    if prob_i is None or prob_j is None:
        return 0.5
    if prob_i <= 0 or prob_j <= 0:
        return 0.5

    score_i = logit(prob_i)
    score_j = logit(prob_j)
    return sigmoid(score_i - score_j)


@matchups_app.command("generate")
def matchups_generate(
    stake_card: pathlib.Path = typer.Option(..., "--stake-card", exists=True, help="Path to stake_card JSON"),
    race_number: Optional[int] = typer.Option(None, "--race", help="Specific race number (default: all)"),
    out_path: Optional[pathlib.Path] = typer.Option(None, "--out", help="Output JSON file"),
    top_n: int = typer.Option(5, "--top", help="Only show top N runners by win prob"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress table output"),
):
    """Generate head-to-head matchup probabilities between runners.

    Uses Bradley-Terry model: P(i beats j) = sigmoid(logit(p_i) - logit(p_j))

    This derived output does NOT modify Lite ordering/math.
    """
    card = json.loads(stake_card.read_text())
    races = card.get("races", [])
    meeting = card.get("meeting", {})

    all_matchups = []
    console = Console()

    for race in races:
        r_num = race.get("race_number")

        # Filter by race number if specified
        if race_number is not None and r_num != race_number:
            continue

        runners = race.get("runners", [])

        # Extract win probabilities
        runner_probs = []
        for runner in runners:
            forecast = runner.get("forecast") or {}
            win_prob = forecast.get("win_prob")
            if win_prob is not None and win_prob > 0:
                runner_probs.append({
                    "runner_number": runner.get("runner_number"),
                    "runner_name": runner.get("runner_name"),
                    "win_prob": win_prob,
                })

        # Sort by win_prob descending, take top N
        runner_probs.sort(key=lambda x: -x["win_prob"])
        runner_probs = runner_probs[:top_n]

        if len(runner_probs) < 2:
            continue

        race_matchups = []

        # Generate pairwise matchups
        for i, r_i in enumerate(runner_probs):
            for j, r_j in enumerate(runner_probs):
                if i >= j:
                    continue  # Only upper triangle

                p_i_beats_j = calculate_pairwise_probability(r_i["win_prob"], r_j["win_prob"])
                edge = abs(p_i_beats_j - 0.5) * 2  # How decisive is the matchup

                matchup = {
                    "race_number": r_num,
                    "runner_a": r_i["runner_number"],
                    "runner_a_name": r_i["runner_name"],
                    "runner_b": r_j["runner_number"],
                    "runner_b_name": r_j["runner_name"],
                    "p_a_beats_b": round(p_i_beats_j, 4),
                    "p_b_beats_a": round(1 - p_i_beats_j, 4),
                    "edge": round(edge, 4),
                    "method": "bradley_terry",
                }
                race_matchups.append(matchup)

        all_matchups.extend(race_matchups)

        # Display table
        if not quiet and race_matchups:
            table = Table(title=f"Race {r_num} - Head-to-Head Matchups (Top {top_n})")
            table.add_column("Runner A", style="cyan")
            table.add_column("vs", justify="center")
            table.add_column("Runner B", style="magenta")
            table.add_column("P(A wins)", justify="right", style="green")
            table.add_column("P(B wins)", justify="right", style="yellow")
            table.add_column("Edge", justify="right")

            for m in race_matchups:
                table.add_row(
                    f"{m['runner_a']}. {m['runner_a_name'][:15]}",
                    "vs",
                    f"{m['runner_b']}. {m['runner_b_name'][:15]}",
                    f"{m['p_a_beats_b']*100:.1f}%",
                    f"{m['p_b_beats_a']*100:.1f}%",
                    f"{m['edge']*100:.1f}%",
                )

            console.print(table)
            console.print()

    # Output JSON
    if out_path:
        output = {
            "meeting_id": meeting.get("meeting_id"),
            "method": "bradley_terry",
            "top_n": top_n,
            "matchup_count": len(all_matchups),
            "matchups": all_matchups,
        }
        out_path.write_text(json.dumps(output, indent=2))
        print(f"Matchups written to {out_path}")

    if not quiet:
        print(f"[bold]Generated {len(all_matchups)} matchup(s)[/bold]")

    return all_matchups


if __name__ == "__main__":
    app()
