"""Deterministic strategy digest generator (PRO/derived-only).

This module reads stake_card + derived simulation outputs and produces
human-friendly digest artifacts (JSON + Markdown). It MUST NOT mutate the
stake_card or change Lite outputs.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from turf.simulation import Bet, stake_for_bet, write_json


def _stable_bet_sort_key(b: Bet) -> Tuple[Any, Any]:
    return (b.race_number, b.runner_number)


def _strategy_reason(bet: Bet, *, stake: float, policy: str) -> str:
    parts: List[str] = []

    ev = bet.ev_1u
    edge = bet.value_edge

    if isinstance(ev, (int, float)):
        parts.append("Positive EV" if ev > 0 else "Non-positive EV")

    if isinstance(edge, (int, float)):
        if edge > 0:
            parts.append("Positive edge")
        elif edge < 0:
            parts.append("Negative edge")

    parts.append(f"Stake via {policy}")

    if stake <= 0:
        parts.append("No stake placed (missing price/prob or policy rules)")

    return "; ".join(parts)


def _reason_tags(bet: Bet, *, stake: float, policy: str) -> List[str]:
    tags: List[str] = []

    if isinstance(bet.ev_1u, (int, float)) and bet.ev_1u > 0:
        tags.append("EV_POSITIVE")
    if isinstance(bet.value_edge, (int, float)) and bet.value_edge > 0:
        tags.append("VALUE_EDGE_POSITIVE")
    if not bet.has_price_prob:
        tags.append("MISSING_PRICE_OR_PROB")

    if policy == "flat":
        tags.append("POLICY_FLAT")
    elif policy == "kelly":
        tags.append("POLICY_KELLY")
    elif policy == "fractional_kelly":
        tags.append("POLICY_FRACTIONAL_KELLY")

    if stake <= 0:
        tags.append("NO_STAKE")

    return sorted(set(tags))


def _meeting_meta(stake_card: Dict[str, Any]) -> Dict[str, str]:
    meeting = stake_card.get("meeting", {}) or {}
    meeting_id = meeting.get("meeting_id") or stake_card.get("meeting_id") or "unknown_meeting"
    date_local = meeting.get("date_local") or stake_card.get("date_local") or "0000-00-00"
    return {"meeting_id": str(meeting_id), "date_local": str(date_local)}


def build_strategy_digest(
    *,
    stake_card: Dict[str, Any],
    bets: List[Bet],
    selection_rules: Dict[str, Any],
    bankroll_policy: Dict[str, Any],
    simulation_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a deterministic digest payload (JSON-serializable)."""

    policy = str(bankroll_policy.get("policy") or "flat")
    bankroll_start = float(bankroll_policy.get("bankroll_start") or 0.0)
    flat_stake = float(bankroll_policy.get("flat_stake") or 0.0)
    kelly_fraction = float(bankroll_policy.get("kelly_fraction") or 0.0)
    max_stake_frac = float(bankroll_policy.get("max_stake_frac") or 0.0)

    bet_rows: List[Dict[str, Any]] = []
    for b in sorted(list(bets), key=_stable_bet_sort_key):
        stake = stake_for_bet(
            policy=policy,
            bankroll=bankroll_start,
            win_prob=b.win_prob,
            odds_dec=b.odds_dec,
            flat_stake=flat_stake,
            kelly_fraction=kelly_fraction,
            max_stake_frac=max_stake_frac,
        )

        row = asdict(b)
        row["stake"] = float(stake)
        row["stake_policy"] = policy
        row["strategy_reason"] = _strategy_reason(b, stake=stake, policy=policy)
        row["reason_tags"] = _reason_tags(b, stake=stake, policy=policy)
        bet_rows.append(row)

    total_stake = sum(float(r.get("stake") or 0.0) for r in bet_rows)

    expected_profit = 0.0
    for r in bet_rows:
        stake = float(r.get("stake") or 0.0)
        ev_1u = r.get("ev_1u")
        if isinstance(ev_1u, (int, float)):
            expected_profit += stake * float(ev_1u)

    digest: Dict[str, Any] = {
        "digest_version": "DIGEST_V1",
        "meeting": _meeting_meta(stake_card),
        "selection_rules": selection_rules,
        "bankroll_policy": bankroll_policy,
        "bets": bet_rows,
        "totals": {
            "bets_selected": len(bet_rows),
            "total_stake": round(total_stake, 2),
            "expected_profit": round(expected_profit, 2),
            "expected_roi": round((expected_profit / total_stake), 6) if total_stake > 0 else 0.0,
        },
    }

    if simulation_summary is not None:
        digest["simulation"] = simulation_summary

    return digest


def render_digest_markdown(digest: Dict[str, Any]) -> str:
    meeting = digest.get("meeting", {}) or {}
    meeting_id = meeting.get("meeting_id", "unknown_meeting")
    date_local = meeting.get("date_local", "0000-00-00")

    pol = digest.get("bankroll_policy", {}) or {}
    policy = pol.get("policy", "flat")

    lines: List[str] = []
    lines.append("# TURF Digest (V1)")
    lines.append(f"Meeting: {meeting_id}")
    lines.append(f"Date: {date_local}")
    lines.append("")
    lines.append("## Policy")
    lines.append(f"- Policy: {policy}")
    lines.append(f"- Bankroll start: ${pol.get('bankroll_start', 0.0)}")
    lines.append(f"- Flat stake: ${pol.get('flat_stake', 0.0)}")
    lines.append(f"- Kelly fraction: {pol.get('kelly_fraction', 0.0)}")
    lines.append(f"- Max stake frac: {pol.get('max_stake_frac', 0.0)}")
    lines.append("")
    lines.append("## Bets")

    bets = digest.get("bets", []) or []
    if not bets:
        lines.append("- (none)")
    else:
        for i, b in enumerate(bets, start=1):
            lines.append(f"{i}. R{b.get('race_number')} #{b.get('runner_number')}")
            lines.append(
                f"   - Odds: {b.get('odds_dec')} | WinProb: {b.get('win_prob')} | EV_1u: {b.get('ev_1u')} | Edge: {b.get('value_edge')}"
            )
            lines.append(f"   - Stake: ${b.get('stake')} ({b.get('stake_policy')})")
            lines.append(f"   - Why: {b.get('strategy_reason', '')}")
            tags = b.get("reason_tags", [])
            lines.append(f"   - Tags: {', '.join(tags) if isinstance(tags, list) else tags}")
            lines.append("")

    totals = digest.get("totals", {}) or {}
    lines.append("## Totals")
    lines.append(f"- Bets: {totals.get('bets_selected', 0)}")
    lines.append(f"- Total stake: ${totals.get('total_stake', 0.0)}")
    lines.append(f"- Expected profit: ${totals.get('expected_profit', 0.0)}")
    lines.append(f"- Expected ROI: {totals.get('expected_roi', 0.0)}")
    lines.append("")

    sim = digest.get("simulation")
    if isinstance(sim, dict):
        cfg = sim.get("config", {}) or {}
        res = sim.get("results", {}) or {}
        lines.append("## Simulation (seeded)")
        lines.append(f"- Seed: {cfg.get('seed')} | Iters: {cfg.get('iters')} | Policy: {cfg.get('policy')}")
        lines.append(f"- Mean final: ${res.get('mean_final')} | Median final: ${res.get('median_final')}")
        lines.append(f"- P05: ${res.get('p05_final')} | P95: ${res.get('p95_final')}")
        lines.append("")

    return "\n".join(lines)


def write_strategy_digest(*, out_dir: str, digest: Dict[str, Any], filename_base: str = "strategy_digest") -> None:
    """Write digest JSON + Markdown deterministically."""
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    write_json(out / f"{filename_base}.json", digest)
    (out / f"{filename_base}.md").write_text(render_digest_markdown(digest), encoding="utf-8")

