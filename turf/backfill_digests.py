from __future__ import annotations

"""Deterministic digest backfill helper (derived-only)."""

import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from engine.turf_engine_pro import (
    apply_pro_overlay_to_stake_card,
    build_runner_vector,
    pro_overlay_logit_win_place_v0,
)
from turf.compile_lite import RunnerInput, compile_stake_card, merge_odds_into_market
from turf.daily_digest import build_daily_digest
from turf.digest_pages import render_digest_pages
from turf.feature_flags import resolve_feature_flags
from turf.parse_odds import parse_generic_odds_table, parsed_odds_to_market
from turf.parse_ra import (
    parse_meeting_html,
    parsed_race_to_market_snapshot,
    parsed_race_to_speed_sidecar,
)


AU_TZ = ZoneInfo("Australia/Sydney")


@dataclass(frozen=True)
class BackfillConfig:
    from_date: Optional[str]
    to_date: Optional[str]
    days: int
    out_dir: Path
    stake_cards_dir: Optional[Path]
    prefer_pro: bool = True
    simulate: bool = False
    seed: int = 1337
    write_per_meeting: bool = True
    render_html: bool = True


def _au_today() -> date:
    return datetime.now(tz=AU_TZ).date()


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _date_range(
    *,
    from_date: Optional[str],
    to_date: Optional[str],
    days: int,
    today_provider: Callable[[], date] = _au_today,
) -> List[date]:
    if days <= 0:
        raise ValueError("days must be positive")

    if from_date and to_date:
        start = _parse_date(from_date)
        end = _parse_date(to_date)
    elif from_date:
        start = _parse_date(from_date)
        end = start + timedelta(days=days - 1)
    elif to_date:
        end = _parse_date(to_date)
        start = end - timedelta(days=days - 1)
    else:
        end = today_provider()
        start = end - timedelta(days=days - 1)

    if start > end:
        raise ValueError("from_date cannot be after to_date")

    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _write_index_markdown(out_path: Path, entries: Sequence[Dict[str, object]], config: BackfillConfig) -> None:
    lines: List[str] = []
    lines.append("# TURF digest backfill index")
    lines.append("")
    lines.append("## Config")
    lines.append(f"- from_date: {config.from_date}")
    lines.append(f"- to_date: {config.to_date}")
    lines.append(f"- days: {config.days}")
    lines.append(f"- prefer_pro: {config.prefer_pro}")
    lines.append(f"- simulate: {config.simulate}")
    lines.append(f"- seed: {config.seed}")
    lines.append(f"- write_per_meeting: {config.write_per_meeting}")
    lines.append(f"- render_html: {config.render_html}")
    lines.append("")
    lines.append("## Dates")
    for entry in entries:
        date_str = entry.get("date") or ""
        lines.append(f"### {date_str}")
        lines.append(f"- source: {entry.get('source')}")
        lines.append(f"- stake_cards: {entry.get('stake_cards_path')}")
        derived = entry.get("derived") or {}
        public = entry.get("public") or {}
        for key in ("daily_digest_json", "daily_digest_md", "meetings_dir"):
            if derived.get(key):
                lines.append(f"- {key}: {derived.get(key)}")
        for key in ("daily_digest_html", "index_html"):
            if public.get(key):
                lines.append(f"- {key}: {public.get(key)}")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n")


def _load_demo_artifacts(date_str: str) -> Tuple[dict, dict, dict]:
    meeting_html = Path("data/demo_meeting.html")
    odds_html = Path("data/demo_odds.html")
    meeting_id = f"DEMO_{date_str}"
    race_number = 1

    parsed = parse_meeting_html(
        meeting_html.read_text(),
        meeting_id=meeting_id,
        race_number=race_number,
        captured_at=f"{date_str}T10:00:00+11:00",
    )
    market = parsed_race_to_market_snapshot(parsed)
    speed = parsed_race_to_speed_sidecar(parsed)

    odds_rows = parse_generic_odds_table(odds_html.read_text())
    odds = parsed_odds_to_market(odds_rows, meeting_id, race_number, f"{date_str}T10:01:00+11:00")
    return market, speed, odds


def _join_runner_inputs(market: dict, speed: dict) -> List[RunnerInput]:
    joined: List[RunnerInput] = []
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
        "track_condition_raw": market.get("race", {}).get("track_condition_raw")
        or market.get("meeting", {}).get("track_condition_raw"),
        "field_size": len(runners),
        "runners": runners,
    }


def _generate_demo_stake_cards(date_str: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    market, speed, odds = _load_demo_artifacts(date_str)
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
    price_map = {
        row.get("runner_number"): (row.get("odds_minimal") or {}).get("price_now_dec")
        for row in merged_market.get("runners", [])
    }
    forecasts = pro_overlay_logit_win_place_v0(
        runner_vector_payload.get("runners", []),
        price_map,
        stake_card.get("engine_context", {}).get("degrade_mode", "NORMAL"),
        stake_card.get("engine_context", {}).get("warnings", []),
    )
    feature_flags = resolve_feature_flags(
        {
            "ev_bands": False,
            "race_summary": False,
        }
    )
    stake_card_pro = apply_pro_overlay_to_stake_card(
        stake_card,
        runner_vector_payload,
        forecasts,
        feature_flags=feature_flags,
    )

    (out_dir / "stake_card.json").write_text(json.dumps(stake_card, indent=2))
    (out_dir / "stake_card_pro.json").write_text(json.dumps(stake_card_pro, indent=2))
    (out_dir / "runner_vector.json").write_text(json.dumps(runner_vector_payload, indent=2))


def _copy_stake_cards_for_date(source_root: Path, date_str: str, dest_dir: Path) -> bool:
    candidate = source_root / date_str
    if not candidate.exists() or not candidate.is_dir():
        return False

    files = [p for p in candidate.glob("*.json") if p.is_file() and "stake_card" in p.name]
    if not files:
        return False

    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(files, key=lambda p: str(p)):
        dest = dest_dir / src.name
        dest.write_text(src.read_text())
    return True


def backfill_digests(config: BackfillConfig) -> Dict[str, object]:
    out_dir = config.out_dir.resolve()
    dates = _date_range(from_date=config.from_date, to_date=config.to_date, days=config.days)
    entries: List[Dict[str, object]] = []

    for dt in dates:
        date_str = dt.isoformat()
        day_root = out_dir / date_str
        if day_root.exists():
            shutil.rmtree(day_root)

        derived_dir = day_root / "derived"
        public_derived_dir = day_root / "public" / "derived" if config.render_html else None
        stake_cards_workdir = day_root / "stake_cards"

        used_provided = False
        if config.stake_cards_dir:
            used_provided = _copy_stake_cards_for_date(config.stake_cards_dir, date_str, stake_cards_workdir)

        if not used_provided:
            _generate_demo_stake_cards(date_str, stake_cards_workdir)

        daily = build_daily_digest(
            stake_cards_dir=stake_cards_workdir,
            out_dir=derived_dir,
            prefer_pro=config.prefer_pro,
            write_per_meeting=config.write_per_meeting,
            simulate=config.simulate,
            seed=config.seed,
        )

        public_info: Dict[str, object] = {}
        if config.render_html and public_derived_dir is not None:
            public_derived_dir.mkdir(parents=True, exist_ok=True)
            daily_html, meeting_htmls = render_digest_pages(derived_dir=derived_dir, public_derived_dir=public_derived_dir)
            if daily_html:
                public_info["daily_digest_html"] = str(daily_html.relative_to(out_dir))
            public_info["index_html"] = str((public_derived_dir / "index.html").relative_to(out_dir))
            if meeting_htmls:
                public_info["meeting_digest_html"] = [str(p.relative_to(out_dir)) for p in meeting_htmls]

        meetings_dir = derived_dir / "meetings"
        derived_info: Dict[str, object] = {
            "daily_digest_json": str((derived_dir / "daily_digest.json").relative_to(out_dir)),
            "daily_digest_md": str((derived_dir / "daily_digest.md").relative_to(out_dir)),
        }
        if meetings_dir.exists():
            derived_info["meetings_dir"] = str(meetings_dir.relative_to(out_dir))

        entries.append(
            {
                "date": date_str,
                "source": "provided" if used_provided else "DEMO",
                "stake_cards_path": str(stake_cards_workdir.relative_to(out_dir)),
                "derived": derived_info,
                "public": public_info,
                "digest_counts": daily.get("counts", {}),
                "config": {
                    "prefer_pro": config.prefer_pro,
                    "simulate": config.simulate,
                    "seed": config.seed,
                    "write_per_meeting": config.write_per_meeting,
                    "render_html": config.render_html,
                },
            }
        )

    index_payload: Dict[str, object] = {
        "config": {
            "from_date": config.from_date,
            "to_date": config.to_date,
            "days": config.days,
            "prefer_pro": config.prefer_pro,
            "simulate": config.simulate,
            "seed": config.seed,
            "write_per_meeting": config.write_per_meeting,
            "render_html": config.render_html,
            "stake_cards_dir": str(config.stake_cards_dir) if config.stake_cards_dir else None,
        },
        "dates": entries,
    }

    _write_json(out_dir / "index.json", index_payload)
    _write_index_markdown(out_dir / "index.md", entries, config)

    return index_payload
