from __future__ import annotations

"""End-to-end collection pipeline: RA capture + odds + stake cards + digests.

This module orchestrates:
1. Discover races from captured RA HTML (or fetch if network available)
2. Capture and parse RA data
3. Fetch/capture market odds (via pluggable adapter)
4. Merge odds into market snapshots
5. Compile stake cards (Lite)
6. Optionally apply PRO overlay
7. Write stake cards to output directory
8. Generate daily digests

The pipeline is designed for determinism:
- Same captured inputs always produce identical outputs
- All operations are offline-capable with fixtures
- No mutation of input files
"""

import copy
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from turf.compile_lite import RunnerInput, compile_stake_card, merge_odds_into_market
from turf.odds_collect import (
    OddsAdapter,
    OddsSnapshot,
    get_odds_adapter,
    odds_snapshot_to_merge_format,
)
from turf.ra_collect import (
    MeetingCapture,
    RaceCapture,
    captured_race_to_artifacts,
    discover_captured_meetings,
    load_captured_meeting,
)

SYDNEY_TZ = ZoneInfo("Australia/Sydney")


@dataclass
class PipelineConfig:
    """Configuration for the collection pipeline."""

    date_local: str
    capture_dir: Path
    out_dir: Path
    odds_source: str = "none"
    odds_fixtures_dir: Optional[Path] = None
    prefer_pro: bool = True
    default_distance_m: int = 1200


@dataclass
class RaceArtifacts:
    """Artifacts for a single race."""

    meeting_id: str
    race_number: int
    date_local: str
    market_snapshot: dict
    speed_sidecar: dict
    odds_snapshot: Optional[OddsSnapshot]
    merged_market: dict
    stake_card: dict
    stake_card_pro: Optional[dict]


@dataclass
class MeetingArtifacts:
    """Artifacts for a complete meeting."""

    meeting_id: str
    date_local: str
    races: List[RaceArtifacts]


@dataclass
class PipelineResult:
    """Result of running the collection pipeline."""

    date_local: str
    meetings: List[MeetingArtifacts]
    stake_card_paths: List[Path]
    digest_path: Optional[Path]
    errors: List[str]


def _today_local(tz: ZoneInfo = SYDNEY_TZ) -> str:
    """Today's date in YYYY-MM-DD format."""
    return datetime.now(tz).date().isoformat()


def _write_json(path: Path, data: dict) -> None:
    """Write JSON with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _deep_copy(data: dict) -> dict:
    """Deep copy a dict to avoid mutation."""
    return copy.deepcopy(data)


def _join_runner_inputs(market: dict, sidecar: dict) -> List[RunnerInput]:
    """Join market snapshot and speed sidecar into RunnerInput list."""
    speed_map = {r.get("runner_number"): r for r in sidecar.get("runners", [])}
    joined = []
    for runner in market.get("runners", []):
        rn = runner.get("runner_number")
        sidecar_data = speed_map.get(rn, {})
        joined.append(
            RunnerInput(
                runner_number=rn,
                runner_name=runner.get("runner_name", f"Runner {rn}"),
                barrier=runner.get("barrier"),
                price_now_dec=(runner.get("odds_minimal") or {}).get("price_now_dec"),
                map_role_inferred=sidecar_data.get("map_role_inferred"),
                avg_speed_mps=sidecar_data.get("avg_speed_mps"),
            )
        )
    return joined


def _stake_card_filename(meeting_id: str, race_number: int, pro: bool = False) -> str:
    """Generate deterministic stake card filename."""
    suffix = "_pro" if pro else ""
    return f"stake_card_r{race_number}{suffix}.json"


def _try_apply_pro_overlay(stake_card: dict, market: dict, sidecar: dict) -> Optional[dict]:
    """Try to apply PRO overlay if engine module is available."""
    try:
        from engine.turf_engine_pro import (
            apply_pro_overlay_to_stake_card,
            build_runner_vector,
            pro_overlay_logit_win_place_v0,
        )
        from turf.feature_flags import resolve_feature_flags

        # Build lite scores map
        race = (stake_card.get("races") or [{}])[0]
        lite_scores = {}
        for runner in race.get("runners", []):
            lite_scores[runner.get("runner_number")] = runner.get("lite_score", 0.5)

        # Build engine inputs
        speed_map = {r.get("runner_number"): r for r in sidecar.get("runners", [])}
        runners = []
        for runner in market.get("runners", []):
            rn = runner.get("runner_number")
            odds_block = runner.get("odds_minimal") or {}
            sidecar_data = speed_map.get(rn, {})
            runners.append(
                {
                    "runner_number": rn,
                    "lite_score": lite_scores.get(rn, 0.5),
                    "price_now_dec": odds_block.get("price_now_dec"),
                    "barrier": runner.get("barrier"),
                    "map_role_inferred": sidecar_data.get("map_role_inferred"),
                    "avg_speed_mps": sidecar_data.get("avg_speed_mps"),
                }
            )

        engine_inputs = {
            "distance_m": market.get("race", {}).get("distance_m"),
            "track_condition_raw": market.get("race", {}).get("track_condition_raw")
            or market.get("meeting", {}).get("track_condition_raw"),
            "field_size": len(runners),
            "runners": runners,
        }

        runner_vector = build_runner_vector(engine_inputs)

        # Get prices for overlay
        prices = {}
        for runner in market.get("runners", []):
            odds_block = runner.get("odds_minimal") or {}
            prices[runner.get("runner_number")] = odds_block.get("price_now_dec")

        forecasts = pro_overlay_logit_win_place_v0(
            runner_vector.get("runners", []),
            prices,
            stake_card.get("engine_context", {}).get("degrade_mode", "NORMAL"),
            stake_card.get("engine_context", {}).get("warnings", []),
        )

        feature_flags = resolve_feature_flags({"ev_bands": True, "race_summary": False})
        stake_card_pro = apply_pro_overlay_to_stake_card(
            _deep_copy(stake_card), runner_vector, forecasts, feature_flags=feature_flags
        )
        return stake_card_pro

    except ImportError:
        # PRO engine not available
        return None
    except Exception:
        # PRO overlay failed, continue without it
        return None


# ---------------------------------------------------------------------------
# Single race processing
# ---------------------------------------------------------------------------


def process_race(
    race_capture: RaceCapture,
    odds_adapter: OddsAdapter,
    *,
    default_distance_m: int = 1200,
    apply_pro: bool = True,
) -> RaceArtifacts:
    """Process a single race: parse RA, fetch odds, compile stake card."""
    # Parse RA HTML into market snapshot and speed sidecar
    market, sidecar = captured_race_to_artifacts(
        race_capture, default_distance_m=default_distance_m
    )

    # Fetch odds from adapter
    runner_names = [r.get("runner_name", "") for r in market.get("runners", [])]
    odds_snapshot = odds_adapter.fetch_odds(
        race_capture.meeting_id,
        race_capture.race_number,
        race_capture.date_local,
        runner_names=runner_names,
    )

    # Merge odds into market snapshot (deep copy to avoid mutation)
    merged_market = _deep_copy(market)
    if odds_snapshot:
        odds_merge_format = odds_snapshot_to_merge_format(odds_snapshot)
        merged_market = merge_odds_into_market(merged_market, odds_merge_format)

    # Build runner inputs
    runner_rows = _join_runner_inputs(merged_market, sidecar)

    # Compile Lite stake card
    stake_card, _ = compile_stake_card(
        meeting=merged_market.get("meeting", {}),
        race=merged_market.get("race", {}),
        runner_rows=runner_rows,
        captured_at=merged_market.get("provenance", {}).get("captured_at", "UNKNOWN"),
        include_overlay=True,
    )

    # Try to apply PRO overlay
    stake_card_pro = None
    if apply_pro:
        stake_card_pro = _try_apply_pro_overlay(stake_card, merged_market, sidecar)

    return RaceArtifacts(
        meeting_id=race_capture.meeting_id,
        race_number=race_capture.race_number,
        date_local=race_capture.date_local,
        market_snapshot=market,
        speed_sidecar=sidecar,
        odds_snapshot=odds_snapshot,
        merged_market=merged_market,
        stake_card=stake_card,
        stake_card_pro=stake_card_pro,
    )


# ---------------------------------------------------------------------------
# Meeting processing
# ---------------------------------------------------------------------------


def process_meeting(
    meeting_capture: MeetingCapture,
    odds_adapter: OddsAdapter,
    *,
    default_distance_m: int = 1200,
    apply_pro: bool = True,
) -> MeetingArtifacts:
    """Process all races in a meeting."""
    races = []
    for race_capture in meeting_capture.races:
        race_artifacts = process_race(
            race_capture,
            odds_adapter,
            default_distance_m=default_distance_m,
            apply_pro=apply_pro,
        )
        races.append(race_artifacts)

    return MeetingArtifacts(
        meeting_id=meeting_capture.meeting_id,
        date_local=meeting_capture.date_local,
        races=races,
    )


# ---------------------------------------------------------------------------
# Write artifacts
# ---------------------------------------------------------------------------


def write_meeting_stake_cards(
    meeting: MeetingArtifacts, out_dir: Path, *, prefer_pro: bool = True
) -> List[Path]:
    """Write stake cards for a meeting to output directory.

    Returns list of written file paths.
    """
    meeting_out = out_dir / meeting.date_local / meeting.meeting_id
    meeting_out.mkdir(parents=True, exist_ok=True)

    written = []
    for race in meeting.races:
        # Always write Lite stake card
        lite_path = meeting_out / _stake_card_filename(
            meeting.meeting_id, race.race_number, pro=False
        )
        _write_json(lite_path, race.stake_card)
        written.append(lite_path)

        # Write PRO stake card if available
        if race.stake_card_pro:
            pro_path = meeting_out / _stake_card_filename(
                meeting.meeting_id, race.race_number, pro=True
            )
            _write_json(pro_path, race.stake_card_pro)
            written.append(pro_path)

    return written


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Run the full collection pipeline for a date.

    1. Discover captured meetings for the date
    2. Process each meeting (parse RA, fetch odds, compile stake cards)
    3. Write stake cards to output directory
    4. Optionally generate daily digest

    Returns PipelineResult with all artifacts and paths.
    """
    errors: List[str] = []
    meetings: List[MeetingArtifacts] = []
    stake_card_paths: List[Path] = []

    # Initialize odds adapter
    odds_adapter = get_odds_adapter(
        config.odds_source, fixtures_dir=config.odds_fixtures_dir
    )

    # Discover captured meetings
    meeting_ids = discover_captured_meetings(config.capture_dir / "ra", config.date_local)

    if not meeting_ids:
        errors.append(f"No captured meetings found for {config.date_local}")
        return PipelineResult(
            date_local=config.date_local,
            meetings=[],
            stake_card_paths=[],
            digest_path=None,
            errors=errors,
        )

    # Process each meeting
    for meeting_id in meeting_ids:
        try:
            meeting_capture = load_captured_meeting(
                config.capture_dir / "ra", config.date_local, meeting_id
            )
            if meeting_capture is None:
                errors.append(f"Failed to load meeting {meeting_id}")
                continue

            meeting_artifacts = process_meeting(
                meeting_capture,
                odds_adapter,
                default_distance_m=config.default_distance_m,
                apply_pro=config.prefer_pro,
            )
            meetings.append(meeting_artifacts)

            # Write stake cards
            paths = write_meeting_stake_cards(
                meeting_artifacts, config.out_dir, prefer_pro=config.prefer_pro
            )
            stake_card_paths.extend(paths)

        except Exception as e:
            errors.append(f"Error processing meeting {meeting_id}: {e}")

    return PipelineResult(
        date_local=config.date_local,
        meetings=meetings,
        stake_card_paths=stake_card_paths,
        digest_path=None,  # Digest is generated separately via CLI
        errors=errors,
    )


def run_pipeline_with_digest(
    config: PipelineConfig,
    *,
    digest_out_dir: Optional[Path] = None,
    simulate: bool = False,
    seed: int = 1337,
    write_per_meeting: bool = False,
) -> PipelineResult:
    """Run pipeline and generate daily digest.

    This is a convenience function that runs the full pipeline
    and then generates the daily digest from the output stake cards.
    """
    from turf.daily_digest import build_daily_digest

    result = run_pipeline(config)

    if result.stake_card_paths:
        # Generate digest from the stake cards directory
        stake_cards_dir = config.out_dir / config.date_local
        out_dir = digest_out_dir or (config.out_dir / "digests" / config.date_local)

        build_daily_digest(
            stake_cards_dir=stake_cards_dir,
            out_dir=out_dir,
            prefer_pro=config.prefer_pro,
            write_per_meeting=write_per_meeting,
            simulate=simulate,
            seed=seed,
        )
        result.digest_path = out_dir / "daily_digest.json"

    return result
