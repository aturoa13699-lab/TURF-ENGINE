from __future__ import annotations

"""Deterministic Lite compiler and overlay helpers."""

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

NEUTRAL = 0.50


@dataclass
class RunnerInput:
    runner_number: int
    runner_name: str
    barrier: int | None
    price_now_dec: float | None
    map_role_inferred: str | None
    avg_speed_mps: float | None


@dataclass
class RunnerOutput:
    runner_number: int
    runner_name: str
    lite_score: float
    lite_tag: str
    components: Dict[str, float]
    price_now_dec: float | None
    forecast: Dict[str, float | None]


def _finite_number(value: float | None) -> bool:
    return value is not None and isinstance(value, (int, float)) and math.isfinite(value)


def _valid_price(price: float | None) -> bool:
    return _finite_number(price) and price > 1.0


def _valid_speed(speed: float | None) -> bool:
    return _finite_number(speed) and speed >= 0


def _market_rank(runners: Iterable[RunnerInput]) -> Dict[int, float]:
    valid = [(r.runner_number, 1.0 / r.price_now_dec) for r in runners if _valid_price(r.price_now_dec)]
    if not valid:
        return {r.runner_number: NEUTRAL for r in runners}
    total = sum(v for _, v in valid)
    ratios = {num: val / total for num, val in valid}
    for r in runners:
        ratios.setdefault(r.runner_number, NEUTRAL)
    return ratios


ROLE_BASES = {
    "LEAD": 0.62,
    "ON_PACE": 0.58,
    "MID": 0.50,
    "BACK": 0.42,
    "UNKNOWN": 0.50,
}


def _barrier_percentiles(runners: List[RunnerInput]) -> Dict[int, float]:
    present = [(r.runner_number, r.barrier) for r in runners if isinstance(r.barrier, int) and r.barrier >= 1]
    if not present:
        return {r.runner_number: 0.5 for r in runners}
    present_sorted = sorted(present, key=lambda t: (t[1], t[0]))
    n = len(present_sorted)
    denom = max(1, n - 1)
    pct = {num: (rank - 1) / denom for rank, (num, _) in enumerate(present_sorted, start=1)}
    for r in runners:
        pct.setdefault(r.runner_number, 0.5)
    return pct


def _barrier_delta(distance_m: int, pct: float) -> float:
    if distance_m <= 1300:
        inside, wide = (0.03, -0.05)
    elif distance_m <= 1700:
        inside, wide = (0.02, -0.04)
    else:
        inside, wide = (0.01, -0.03)
    if pct <= 0.25:
        return inside
    if pct >= 0.75:
        return wide
    return 0.0


def _map_adv(runners: List[RunnerInput], distance_m: int) -> Dict[int, float]:
    pct_map = _barrier_percentiles(runners)
    raw_values: Dict[int, float] = {}
    for r in runners:
        role = (r.map_role_inferred or "UNKNOWN").upper()
        base = ROLE_BASES.get(role, ROLE_BASES["UNKNOWN"])
        delta = _barrier_delta(distance_m, pct_map[r.runner_number])
        raw_values[r.runner_number] = base + delta
    mean_raw = sum(raw_values.values()) / len(raw_values)
    adjusted = {num: max(0.0, min(1.0, 0.5 + (val - mean_raw))) for num, val in raw_values.items()}
    return adjusted


def _speed_proxy(runners: List[RunnerInput]) -> Dict[int, float]:
    speeds = [(r.runner_number, r.avg_speed_mps) for r in runners if _valid_speed(r.avg_speed_mps)]
    if len(speeds) < 3:
        return {r.runner_number: NEUTRAL for r in runners}
    values = [v for _, v in speeds]
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(max(variance, 1e-9))
    proxies = {num: 0.5 + max(-3.0, min(3.0, (val - mean) / std)) / 6.0 for num, val in speeds}
    for r in runners:
        proxies.setdefault(r.runner_number, NEUTRAL)
    return proxies


def _lite_tag(score: float) -> str:
    if score >= 0.68:
        return "A_LITE"
    if score >= 0.58:
        return "B_LITE"
    return "PASS_LITE"


def _featureless_overlay(
    lite_scores: Dict[int, float],
    market_prob: Dict[int, float],
    prices: Dict[int, float | None],
    degrade_mode: str,
    warnings: List[str],
) -> Dict[int, Dict[str, float | None]]:
    tau = 0.12
    if degrade_mode == "MARKET_ONLY":
        tau = 0.18
    elif degrade_mode == "PARTIAL_SIDECAR":
        tau = 0.14
    if "FEW_VALID_SPEEDS_NEUTRALIZED" in warnings:
        tau = max(tau, 0.14)
    if "ALL_PRICES_INVALID" in warnings:
        tau = max(tau, 0.16)

    exp_vals = {num: math.exp(score / tau) for num, score in lite_scores.items()}
    z = sum(exp_vals.values())
    p_raw = {num: val / z for num, val in exp_vals.items()}

    if degrade_mode == "MARKET_ONLY":
        alpha = 0.70
    elif degrade_mode == "PARTIAL_SIDECAR":
        alpha = 0.40
    else:
        alpha = 0.25

    win_prob = {num: (1 - alpha) * p_raw[num] + alpha * market_prob[num] for num in lite_scores}

    place_prob: Dict[int, float] = {}
    for num, prob in win_prob.items():
        acc = 0.0
        for k, p_k in win_prob.items():
            if k == num:
                continue
            denom = 1.0 - p_k
            acc += p_k * (prob / denom) if denom > 0 else 0.0
        place_prob[num] = max(0.0, min(1.0, prob + acc))

    warnings_set = set(warnings)
    if degrade_mode == "NORMAL" and not warnings_set:
        certainty = 1.00
    elif warnings_set & {"SOME_PRICES_INVALID", "JOIN_MISS"}:
        certainty = 0.80
    elif warnings_set & {"ALL_PRICES_INVALID", "FEW_VALID_SPEEDS_NEUTRALIZED"}:
        certainty = 0.60
    else:
        certainty = 0.80

    forecast: Dict[int, Dict[str, float | None]] = {}
    for num in lite_scores:
        price = prices.get(num)
        has_price = _valid_price(price)
        ev_1u = None
        if has_price:
            b = price - 1.0
            ev_1u = win_prob[num] * b - (1.0 - win_prob[num])
        forecast[num] = {
            "win_prob": win_prob[num],
            "place_prob": place_prob[num],
            "market_prob": market_prob[num],
            "value_edge": win_prob[num] - market_prob[num],
            "ev_1u": ev_1u,
            "certainty": certainty,
        }
    return forecast


def compile_stake_card(
    *,
    meeting: dict,
    race: dict,
    runner_rows: List[RunnerInput],
    captured_at: str,
    include_overlay: bool = True,
) -> Tuple[dict, List[RunnerOutput]]:
    warnings: List[str] = []
    prices_valid = [_valid_price(r.price_now_dec) for r in runner_rows]
    speeds_valid = [_valid_speed(r.avg_speed_mps) for r in runner_rows]

    if any(not p for p in prices_valid):
        if any(prices_valid):
            warnings.append("SOME_PRICES_INVALID")
        else:
            warnings.append("ALL_PRICES_INVALID")

    if sum(speeds_valid) < 3:
        warnings.append("FEW_VALID_SPEEDS_NEUTRALIZED")

    degrade_mode: str
    if sum(speeds_valid) == 0:
        degrade_mode = "MARKET_ONLY"
    elif sum(speeds_valid) < len(runner_rows) or sum(prices_valid) == 0:
        degrade_mode = "PARTIAL_SIDECAR"
    else:
        degrade_mode = "NORMAL"

    market_rank = _market_rank(runner_rows)
    speed_proxy = _speed_proxy(runner_rows)
    map_adv = _map_adv(runner_rows, race.get("distance_m") or 1200)

    lite_scores: Dict[int, float] = {}
    outputs: List[RunnerOutput] = []

    for r in runner_rows:
        score = 0.45 * market_rank[r.runner_number] + 0.35 * map_adv[r.runner_number] + 0.20 * speed_proxy[r.runner_number]
        score = max(0.0, min(1.0, score))
        lite_scores[r.runner_number] = score
        outputs.append(
            RunnerOutput(
                runner_number=r.runner_number,
                runner_name=r.runner_name,
                lite_score=score,
                lite_tag=_lite_tag(score),
                components={
                    "MarketRankN": market_rank[r.runner_number],
                    "MapAdvN": map_adv[r.runner_number],
                    "SpeedProxyN": speed_proxy[r.runner_number],
                },
                price_now_dec=r.price_now_dec,
                forecast={},
            )
        )

    market_prob = market_rank
    if "ALL_PRICES_INVALID" in warnings:
        n = len(runner_rows)
        market_prob = {r.runner_number: 1.0 / n for r in runner_rows}

    price_map = {r.runner_number: r.price_now_dec for r in runner_rows}
    if include_overlay:
        forecasts = _featureless_overlay(lite_scores, market_prob, price_map, degrade_mode, warnings)
        for out in outputs:
            out.forecast = forecasts[out.runner_number]

    outputs.sort(
        key=lambda r: (
            -round(r.lite_score, 6),
            -round(r.components["MapAdvN"], 6),
            -round(r.components["MarketRankN"], 6),
            -round(r.components["SpeedProxyN"], 6),
            runner_price_anchor(runner_rows, r.runner_number),
            r.runner_number,
        )
    )

    warnings_sorted = sorted(set(warnings))

    stake_card = {
        "engine_context": {
            "engine_spec_id": "TURF_ENGINE_LITE_AU",
            "engine_version": "0.2.1p2",
            "lite_version": "0.2.1p2",
            "degrade_mode": degrade_mode,
            "warnings": warnings_sorted,
            "inputs_hash": "INLINE",
            "forecast_params": {
                "tau": 0.12,
                "alpha": 0.25,
                "market_prob_basis": "valid_prices_only|uniform_if_empty",
                "notes": "overlay_only_featureless",
            }
            if include_overlay
            else None,
            "debug": {
                "overlay_writer": "LITE_WRAPPER_SOFTMAX_BLEND" if include_overlay else None,
            },
        },
        "meeting": meeting,
        "races": [
            {
                "race_number": race.get("race_number"),
                "distance_m": race.get("distance_m"),
                "runners": [
                    {
                        "runner_number": o.runner_number,
                        "runner_name": o.runner_name,
                        "lite_score": o.lite_score,
                        "lite_tag": o.lite_tag,
                        "lite_components": o.components,
                        "odds_minimal": {"price_now_dec": o.price_now_dec}
                        if o.price_now_dec is not None
                        else None,
                        "forecast": o.forecast or None,
                    }
                    for o in outputs
                ],
            }
        ],
    }
    return stake_card, outputs


def runner_price_anchor(rows: List[RunnerInput], runner_number: int) -> float:
    price = next((r.price_now_dec for r in rows if r.runner_number == runner_number), None)
    if _valid_price(price):
        return price  # shorter is better in tie-break
    return float("inf")


def merge_odds_into_market(market_snapshot: dict, odds_market: dict) -> dict:
    prices = {row["runner_name"].strip().lower(): row.get("price_now_dec") for row in odds_market.get("runners", [])}
    for runner in market_snapshot.get("runners", []):
        key = runner.get("runner_name", "").strip().lower()
        if key in prices:
            runner.setdefault("odds_minimal", {})["price_now_dec"] = prices[key]
    return market_snapshot
