"""Deterministic simulation and bankroll helpers (PRO/derived-only).

Outputs from this module are intended for derived/PRO artifacts only. Lite
outputs must remain untouched. All randomness is seeded via stdlib random.Random
to keep results stable for the same inputs and seed.
"""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional


def _round_currency(value: float) -> float:
    """Round monetary values deterministically to 2 decimal places."""

    return round(value, 2)


def sha256_file(path: Path) -> str:
    data = path.read_bytes()
    return sha256(data).hexdigest()


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


@dataclass(frozen=True)
class Bet:
    meeting_id: str
    date_local: str
    race_number: Any
    runner_number: Any
    odds_dec: Optional[float]
    win_prob: Optional[float]
    ev_1u: Optional[float]
    value_edge: Optional[float]

    @property
    def has_price_prob(self) -> bool:
        return self.odds_dec is not None and self.win_prob is not None


def select_bets_from_stake_card(
    stake_card: Dict[str, Any],
    *,
    require_positive_ev: bool = True,
    min_ev: float | None = None,
    min_edge: float | None = None,
) -> List[Bet]:
    """Select bets deterministically from a stake card.

    Default rule: forecast.ev_1u must exist and be > 0.0 unless explicitly
    disabled. Iteration order follows the input races/runners order to keep
    outputs stable.
    """

    bets: List[Bet] = []
    meeting = stake_card.get("meeting", {}) or {}
    meeting_id = meeting.get("meeting_id") or stake_card.get("meeting_id") or "unknown_meeting"
    date_local = meeting.get("date_local") or stake_card.get("date_local") or "0000-00-00"

    for race in stake_card.get("races", []):
        race_number = race.get("race_number")
        for runner in race.get("runners", []):
            forecast = runner.get("forecast") or {}
            ev = forecast.get("ev_1u")
            edge = forecast.get("value_edge")
            if ev is None:
                continue
            if require_positive_ev and ev <= 0:
                continue
            if min_ev is not None and ev < min_ev:
                continue
            if min_edge is not None and edge is not None and edge < min_edge:
                continue

            odds_block = runner.get("odds_minimal") or {}
            odds_dec = odds_block.get("price_now_dec")
            win_prob = forecast.get("win_prob")

            bets.append(
                Bet(
                    meeting_id=meeting_id,
                    date_local=date_local,
                    race_number=race_number,
                    runner_number=runner.get("runner_number"),
                    odds_dec=odds_dec if isinstance(odds_dec, (int, float)) else None,
                    win_prob=win_prob if isinstance(win_prob, (int, float)) else None,
                    ev_1u=ev if isinstance(ev, (int, float)) else None,
                    value_edge=edge if isinstance(edge, (int, float)) else None,
                )
            )

    return bets


def stake_for_bet(
    *,
    policy: str,
    bankroll: float,
    win_prob: Optional[float],
    odds_dec: Optional[float],
    flat_stake: float,
    kelly_fraction: float,
    max_stake_frac: float,
) -> float:
    """Compute stake size deterministically for a single bet.

    Caps stake at `bankroll * max_stake_frac` and never returns negative.
    """

    if bankroll <= 0:
        return 0.0

    max_stake = bankroll * max_stake_frac
    stake = 0.0

    if policy == "flat":
        stake = flat_stake
    elif policy in {"kelly", "fractional_kelly"}:
        if win_prob is None or odds_dec is None or odds_dec <= 1:
            stake = 0.0
        else:
            b = odds_dec - 1.0
            kelly_fraction_full = (win_prob * b - (1 - win_prob)) / b
            kelly_fraction_full = max(0.0, kelly_fraction_full)
            stake = bankroll * kelly_fraction_full
            if policy == "fractional_kelly":
                stake *= kelly_fraction
    else:
        stake = 0.0

    stake = min(max_stake, stake)
    stake = max(0.0, stake)
    return _round_currency(stake)


def simulate_bankroll(
    *,
    bets: List[Bet],
    iters: int,
    seed: int,
    bankroll_start: float,
    policy: str,
    flat_stake: float,
    kelly_fraction: float,
    max_stake_frac: float,
) -> Dict[str, Any]:
    """Run deterministic Monte Carlo bankroll simulation.

    Bets without price/prob data are skipped (no stake placed).
    """

    rng = random.Random(seed)
    finals: List[float] = []
    bets_considered = len(bets)
    bets_simulated = 0
    skipped_missing = 0

    for _ in range(iters):
        bankroll = float(bankroll_start)
        for bet in bets:
            stake = stake_for_bet(
                policy=policy,
                bankroll=bankroll,
                win_prob=bet.win_prob,
                odds_dec=bet.odds_dec,
                flat_stake=flat_stake,
                kelly_fraction=kelly_fraction,
                max_stake_frac=max_stake_frac,
            )
            if stake <= 0 or not bet.has_price_prob:
                skipped_missing += 1
                continue
            bets_simulated += 1
            bankroll -= stake
            if rng.random() < bet.win_prob:  # type: ignore[arg-type]
                bankroll += stake * (bet.odds_dec or 0.0)
        finals.append(_round_currency(bankroll))

    finals_sorted = sorted(finals)

    def percentile(data: List[float], pct: float) -> float:
        if not data:
            return 0.0
        idx = min(len(data) - 1, max(0, int(len(data) * pct)))
        return data[idx]

    summary = {
        "config": {
            "seed": seed,
            "iters": iters,
            "policy": policy,
            "bankroll_start": bankroll_start,
            "flat_stake": flat_stake,
            "kelly_fraction": kelly_fraction,
            "max_stake_frac": max_stake_frac,
        },
        "counts": {
            "bets_considered": bets_considered,
            "bets_simulated": bets_simulated,
            "bets_skipped_missing": skipped_missing,
        },
        "results": {
            "mean_final": statistics.mean(finals_sorted) if finals_sorted else bankroll_start,
            "median_final": statistics.median(finals_sorted) if finals_sorted else bankroll_start,
            "p05_final": percentile(finals_sorted, 0.05),
            "p95_final": percentile(finals_sorted, 0.95),
            "min_final": finals_sorted[0] if finals_sorted else bankroll_start,
            "max_final": finals_sorted[-1] if finals_sorted else bankroll_start,
        },
    }

    return summary

