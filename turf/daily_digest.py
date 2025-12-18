from __future__ import annotations

"""Plan 071: deterministic multi-stake-card daily digest aggregation (derived-only).

This module aggregates multiple stake-card JSON files from a directory into
single daily digest artifacts. It must:
- remain deterministic
- avoid mutating input payloads
- produce stable ordering across platforms
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from turf.digest import build_strategy_digest
from turf.simulation import select_bets_from_stake_card, simulate_bankroll, write_json


def _meeting_key(payload: Dict[str, Any]) -> Tuple[str, str]:
    meeting = payload.get("meeting", {}) or {}
    meeting_id = meeting.get("meeting_id") or payload.get("meeting_id") or "unknown_meeting"
    date_local = meeting.get("date_local") or payload.get("date_local") or "0000-00-00"
    return str(date_local), str(meeting_id)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def discover_stake_cards(dir_path: Path) -> List[Path]:
    """Deterministically discover candidate stake-card JSON files in a directory."""
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    files = [p for p in dir_path.glob("*.json") if p.is_file()]
    files_sorted = sorted(files, key=lambda p: str(p))
    # Only keep stake-card-ish files.
    return [p for p in files_sorted if "stake_card" in p.name]


def _is_pro_path(p: Path) -> bool:
    return p.name.lower().endswith("_pro.json")


def dedupe_by_meeting(paths: List[Path], *, prefer_pro: bool) -> List[Path]:
    """Choose a single stake card per meeting key (date_local, meeting_id).

    If prefer_pro=True and both lite + pro exist for same key, select pro.
    Output is ordered deterministically by (date_local, meeting_id, path).
    """
    chosen: Dict[Tuple[str, str], Path] = {}
    for p in paths:
        payload = _load_json(p)
        key = _meeting_key(payload)
        prev = chosen.get(key)
        if prev is None:
            chosen[key] = p
            continue
        if prefer_pro and _is_pro_path(p) and not _is_pro_path(prev):
            chosen[key] = p

    items = sorted(chosen.items(), key=lambda kv: (kv[0][0], kv[0][1], str(kv[1])))
    return [p for _, p in items]


def render_daily_digest_markdown(daily: Dict[str, Any]) -> str:
    """Render stable Markdown for the daily digest (no timestamps)."""
    lines: List[str] = []
    cfg = daily.get("config", {}) or {}
    counts = daily.get("counts", {}) or {}
    meetings = daily.get("meetings", []) or []

    lines.append("# TURF Daily Digest")
    lines.append("")
    lines.append(f"- meetings: {counts.get('meetings_included', 0)}")
    lines.append(f"- files_seen: {counts.get('files_seen', 0)}")
    lines.append(f"- policy: {cfg.get('policy')}")
    lines.append(f"- bankroll_start: {cfg.get('bankroll_start')}")
    lines.append(f"- simulate: {cfg.get('simulate')}")
    lines.append("")

    for m in meetings:
        meeting_id = m.get("meeting_id") or "unknown_meeting"
        date_local = m.get("date_local") or "0000-00-00"
        source_path = m.get("source_path") or ""
        bets_count = m.get("bets_count") or 0
        lines.append(f"## {meeting_id} ({date_local})")
        if source_path:
            lines.append(f"- source: {source_path}")
        lines.append(f"- bets: {bets_count}")
        lines.append("")

        # Optional: include a compact bet list if present in the embedded digest.
        digest = m.get("strategy_digest") or {}
        bet_rows = digest.get("bets") or []
        for b in bet_rows:
            # Keep stable formatting; tolerate dict or string.
            if isinstance(b, dict):
                rn = b.get("runner_number")
                bt = b.get("bet_type") or b.get("type") or "BET"
                stake = b.get("stake")
                price = b.get("odds_dec") or b.get("price")
                reason = b.get("reason") or ""
                lines.append(f"- R{b.get('race_number')} #{rn} {bt} stake={stake} price={price} {reason}".rstrip())
            else:
                lines.append(f"- {b}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_daily_digest(
    *,
    stake_cards_dir: Path,
    out_dir: Path,
    prefer_pro: bool = True,
    require_positive_ev: bool = True,
    min_ev: float | None = None,
    min_edge: float | None = None,
    policy: str = "flat",
    bankroll_start: float = 1000.0,
    flat_stake: float = 20.0,
    kelly_fraction: float = 0.25,
    max_stake_frac: float = 0.02,
    simulate: bool = False,
    iters: int = 10_000,
    seed: int = 1337,
) -> Dict[str, Any]:
    """Build and write daily_digest.json + daily_digest.md deterministically."""
    files = discover_stake_cards(stake_cards_dir)
    selected = dedupe_by_meeting(files, prefer_pro=prefer_pro)

    meetings_out: List[Dict[str, Any]] = []

    for p in selected:
        payload = _load_json(p)
        date_local, meeting_id = _meeting_key(payload)

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

        meetings_out.append(
            {
                "meeting_id": meeting_id,
                "date_local": date_local,
                "source_path": str(p),
                "bets_count": len(bets),
                "strategy_digest": digest_payload,
            }
        )

    meetings_out = sorted(meetings_out, key=lambda m: (m.get("date_local") or "0000-00-00", m.get("meeting_id") or "", m.get("source_path") or ""))

    daily: Dict[str, Any] = {
        "config": {
            "stake_cards_dir": str(stake_cards_dir),
            "prefer_pro": prefer_pro,
            "require_positive_ev": require_positive_ev,
            "min_ev": min_ev,
            "min_edge": min_edge,
            "policy": policy,
            "bankroll_start": bankroll_start,
            "flat_stake": flat_stake,
            "kelly_fraction": kelly_fraction,
            "max_stake_frac": max_stake_frac,
            "simulate": simulate,
            "iters": iters,
            "seed": seed,
        },
        "counts": {
            "files_seen": len(files),
            "meetings_included": len(meetings_out),
        },
        "meetings": meetings_out,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "daily_digest.json", daily)
    (out_dir / "daily_digest.md").write_text(render_daily_digest_markdown(daily))
    return daily

