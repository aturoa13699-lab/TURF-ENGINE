from __future__ import annotations

"""Deterministic RunnerVector builder and LOGIT_WIN_PLACE_v0 overlay.

This module keeps the overlay ordering-isolated: it only writes forecast.*
fields and never alters LiteScore ordering.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from turf.feature_flags import resolve_feature_flags
from turf.race_summary import summarize_race
from turf.value import derive_runner_value_fields
from turf.runner_insights import derive_runner_insights, derive_trap_race


def canonical_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def valid_price(price: float | None) -> bool:
    return isinstance(price, (int, float)) and math.isfinite(price) and price > 1.0


def valid_speed(speed: float | None) -> bool:
    return isinstance(speed, (int, float)) and math.isfinite(speed) and speed >= 0


ROLE_INDEX = {"LEAD": 0, "ON_PACE": 1, "MID": 2, "BACK": 3, "UNKNOWN": 4}
TRACK_INDEX = {"FIRM": 0, "GOOD": 1, "SOFT": 2, "HEAVY": 3, "SYNTH": 4, "UNKNOWN": 5}


@dataclass
class RunnerVector:
    runner_number: int
    x: Dict[str, object]


COEFFS_LOGIT_WIN_PLACE_V0 = {
    "b0": -0.20,
    "market_prob": 1.40,
    "lite_score": 1.10,
    "barrier_pct": -0.25,
    "speed_norm": 0.55,
    "days_since_run_norm": -0.15,
    "field_size_norm": -0.10,
    "distance_suit_norm": 0.35,
    "weight_eff_norm": 0.30,
    "class_delta_norm": 0.28,
    "last600_eff_norm": 0.45,
    "pos_delta_norm": 0.20,
    "jockey_sr_norm": 0.18,
    "trainer_sr_norm": 0.12,
    "gear_health_norm": 0.08,
    "map_role_onehot[0]": 0.18,
    "map_role_onehot[1]": 0.10,
    "map_role_onehot[2]": 0.00,
    "map_role_onehot[3]": -0.12,
    "map_role_onehot[4]": 0.00,
    "track_condition_onehot[0]": 0.05,
    "track_condition_onehot[1]": 0.00,
    "track_condition_onehot[2]": -0.03,
    "track_condition_onehot[3]": -0.06,
    "track_condition_onehot[4]": 0.00,
    "track_condition_onehot[5]": 0.00,
}


def _market_prob_from_prices(runners: Iterable[dict]) -> Dict[int, float]:
    valid = [(r["runner_number"], 1.0 / r["price_now_dec"]) for r in runners if valid_price(r.get("price_now_dec"))]
    runner_numbers = [r["runner_number"] for r in runners]
    if valid:
        total = sum(val for _, val in valid)
        probs = {num: val / total for num, val in valid}
    else:
        n = len(runner_numbers) or 1
        probs = {num: 1.0 / n for num in runner_numbers}
    for num in runner_numbers:
        probs.setdefault(num, 0.0)
    return probs


def _barrier_pct(runners: List[dict]) -> Dict[int, float]:
    present = [(r["runner_number"], r.get("barrier")) for r in runners if isinstance(r.get("barrier"), int) and r["barrier"] >= 1]
    if not present:
        return {r["runner_number"]: 0.5 for r in runners}
    present_sorted = sorted(present, key=lambda t: (t[1], t[0]))
    n = len(present_sorted)
    denom = max(1, n - 1)
    pct = {num: (rank - 1) / denom for rank, (num, _) in enumerate(present_sorted, start=1)}
    for r in runners:
        pct.setdefault(r["runner_number"], 0.5)
    return pct


def _speed_norm(runners: List[dict]) -> Dict[int, float]:
    speeds = [(r["runner_number"], r.get("avg_speed_mps")) for r in runners if valid_speed(r.get("avg_speed_mps"))]
    if len(speeds) < 3:
        return {r["runner_number"]: 0.5 for r in runners}
    values = [v for _, v in speeds]
    vmin, vmax = min(values), max(values)
    denom = (vmax - vmin) if (vmax - vmin) > 0 else 1.0
    scaled = {num: (val - vmin) / denom for num, val in speeds}
    for r in runners:
        scaled.setdefault(r["runner_number"], 0.5)
    return scaled


def _map_role_onehot(role: str | None) -> List[int]:
    idx = ROLE_INDEX.get((role or "UNKNOWN").upper(), ROLE_INDEX["UNKNOWN"])
    arr = [0, 0, 0, 0, 0]
    arr[idx] = 1
    return arr


def _track_condition_onehot(raw: str | None) -> List[int]:
    raw_upper = (raw or "").upper()
    if "FIRM" in raw_upper:
        idx = TRACK_INDEX["FIRM"]
    elif "GOOD" in raw_upper:
        idx = TRACK_INDEX["GOOD"]
    elif "SOFT" in raw_upper:
        idx = TRACK_INDEX["SOFT"]
    elif "HEAVY" in raw_upper:
        idx = TRACK_INDEX["HEAVY"]
    elif "SYN" in raw_upper or "POLY" in raw_upper or "TAPETA" in raw_upper:
        idx = TRACK_INDEX["SYNTH"]
    else:
        idx = TRACK_INDEX["UNKNOWN"]
    arr = [0, 0, 0, 0, 0, 0]
    arr[idx] = 1
    return arr


def build_runner_vector(engine_inputs: dict) -> dict:
    """Build runner_vector.v1 style payload from deterministic inputs."""

    runners_raw = engine_inputs.get("runners", [])
    track_condition = engine_inputs.get("track_condition_raw")
    barrier_pct = _barrier_pct(runners_raw)
    speed_norm = _speed_norm(runners_raw)
    market_prob = _market_prob_from_prices(runners_raw)
    track_onehot = _track_condition_onehot(track_condition)
    field_size = engine_inputs.get("field_size") or len(runners_raw)

    vectors: List[RunnerVector] = []
    for r in runners_raw:
        rn = r.get("runner_number")
        days_since_run = r.get("days_since_run")
        dist_bucket_stats = r.get("dist_bucket_stats") or {}
        rating = r.get("rating")
        allocated_weight = r.get("allocated_weight_kg")
        bm_delta = r.get("bm_delta")
        fsp_pct = r.get("fsp_pct")
        pos800, pos400 = r.get("pos800"), r.get("pos400")
        jockey_win = r.get("jockey_win_pct_12m")
        trainer_win = r.get("trainer_win_pct_12m")
        gear_tag = (r.get("gear_health_tag") or "").lower()

        weight_eff_val = None
        if rating is not None and allocated_weight is not None and allocated_weight > 0 and math.isfinite(rating):
            weight_eff_val = rating / allocated_weight

        x = {
            "market_prob": market_prob.get(rn, 0.0),
            "lite_score": clamp(r.get("lite_score", 0.5), 0.0, 1.0),
            "map_role_onehot": _map_role_onehot(r.get("map_role_inferred")),
            "barrier_pct": barrier_pct.get(rn, 0.5),
            "speed_norm": speed_norm.get(rn, 0.5),
            "days_since_run_norm": clamp((days_since_run / 120.0), 0.0, 1.0)
            if isinstance(days_since_run, (int, float)) and days_since_run >= 0 and math.isfinite(days_since_run)
            else 0.5,
            "field_size_norm": clamp((field_size - 2) / 16.0, 0.0, 1.0),
            "distance_suit_norm": clamp(
                (dist_bucket_stats.get("placed", 0) / max(1, dist_bucket_stats.get("starts", 1)))
                if dist_bucket_stats
                else 0.5,
                0.0,
                1.0,
            ),
            "track_condition_onehot": track_onehot,
            "weight_eff_norm": 0.5,
            "class_delta_norm": 0.5,
            "last600_eff_norm": 0.5,
            "pos_delta_norm": 0.5,
            "jockey_sr_norm": clamp((jockey_win / 0.30), 0.0, 1.0) if isinstance(jockey_win, (int, float)) else 0.5,
            "trainer_sr_norm": clamp((trainer_win / 0.30), 0.0, 1.0) if isinstance(trainer_win, (int, float)) else 0.5,
            "gear_health_norm": 0.25 if gear_tag == "bad" else 0.75 if gear_tag == "positive" else 0.5,
        }

        if weight_eff_val is not None:
            x["weight_eff_norm"] = 0.5 + clamp(weight_eff_val, -3.0, 3.0) / 6.0
        if bm_delta is not None and math.isfinite(bm_delta):
            if bm_delta <= -6:
                x["class_delta_norm"] = 1.0
            elif bm_delta >= 6:
                x["class_delta_norm"] = 0.0
            else:
                x["class_delta_norm"] = clamp(0.5 - (bm_delta / 12.0), 0.0, 1.0)
        if fsp_pct is not None and math.isfinite(fsp_pct):
            x["last600_eff_norm"] = clamp(0.50 + 0.0033 * (fsp_pct - 100.0), 0.0, 1.0)
        if isinstance(pos800, int) and isinstance(pos400, int) and field_size:
            delta = (pos800 - pos400) / max(1, field_size - 1)
            x["pos_delta_norm"] = clamp(0.5 + 0.5 * delta, 0.0, 1.0)

        vectors.append(RunnerVector(runner_number=rn, x=x))

    checksum = sha256_hex(canonical_json({"runners": [v.__dict__ for v in vectors]}))
    return {"runners": [v.__dict__ for v in vectors], "debug": {"checksum": checksum}}


def _logistic(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _softmax(values: List[float], tau: float) -> List[float]:
    if not values:
        return []
    m = max(values)
    exps = [math.exp((v - m) / tau) for v in values]
    z = sum(exps)
    return [v / z for v in exps]


def pro_overlay_logit_win_place_v0(
    runner_vectors: List[dict],
    prices_now_dec: Dict[int, float | None],
    degrade_mode: str,
    warnings: List[str],
    coeffs: Dict[str, float] = COEFFS_LOGIT_WIN_PLACE_V0,
    tau: float = 0.12,
) -> Dict[int, Dict[str, float | None]]:
    zs: List[float] = []
    logits: List[float] = []
    runner_numbers: List[int] = []
    for rv in runner_vectors:
        x = rv["x"]
        rn = rv["runner_number"]
        runner_numbers.append(rn)
        z = coeffs["b0"]
        z += coeffs["market_prob"] * x["market_prob"]
        z += coeffs["lite_score"] * x["lite_score"]
        z += coeffs["barrier_pct"] * x["barrier_pct"]
        z += coeffs["speed_norm"] * x["speed_norm"]
        z += coeffs["days_since_run_norm"] * x["days_since_run_norm"]
        z += coeffs["field_size_norm"] * x["field_size_norm"]
        z += coeffs["distance_suit_norm"] * x["distance_suit_norm"]
        z += coeffs["weight_eff_norm"] * x["weight_eff_norm"]
        z += coeffs["class_delta_norm"] * x["class_delta_norm"]
        z += coeffs["last600_eff_norm"] * x["last600_eff_norm"]
        z += coeffs["pos_delta_norm"] * x["pos_delta_norm"]
        z += coeffs["jockey_sr_norm"] * x["jockey_sr_norm"]
        z += coeffs["trainer_sr_norm"] * x["trainer_sr_norm"]
        z += coeffs["gear_health_norm"] * x["gear_health_norm"]
        mr = x["map_role_onehot"]
        tc = x["track_condition_onehot"]
        z += coeffs["map_role_onehot[0]"] * mr[0]
        z += coeffs["map_role_onehot[1]"] * mr[1]
        z += coeffs["map_role_onehot[2]"] * mr[2]
        z += coeffs["map_role_onehot[3]"] * mr[3]
        z += coeffs["map_role_onehot[4]"] * mr[4]
        z += coeffs["track_condition_onehot[0]"] * tc[0]
        z += coeffs["track_condition_onehot[1]"] * tc[1]
        z += coeffs["track_condition_onehot[2]"] * tc[2]
        z += coeffs["track_condition_onehot[3]"] * tc[3]
        z += coeffs["track_condition_onehot[4]"] * tc[4]
        z += coeffs["track_condition_onehot[5]"] * tc[5]
        zs.append(z)
        logits.append(_logistic(z))

    p_win = _softmax(logits, tau)

    market_prob = [rv["x"]["market_prob"] for rv in runner_vectors]
    n = len(runner_vectors)
    p_place: List[float] = []
    for i in range(n):
        acc = 0.0
        for k in range(n):
            if k == i:
                continue
            denom = 1.0 - p_win[k]
            acc += p_win[k] * (p_win[i] / denom) if denom > 0 else 0.0
        p_place.append(clamp(p_win[i] + acc, 0.0, 1.0))

    warnings_set = set(warnings or [])
    if degrade_mode == "NORMAL" and not warnings_set:
        certainty = 1.00
    elif warnings_set & {"SOME_PRICES_INVALID", "JOIN_MISS"}:
        certainty = 0.80
    elif warnings_set & {"ALL_PRICES_INVALID", "FEW_VALID_SPEEDS_NEUTRALIZED"}:
        certainty = 0.60
    else:
        certainty = 0.80

    forecasts: Dict[int, Dict[str, float | None]] = {}
    for idx, rn in enumerate(runner_numbers):
        price = prices_now_dec.get(rn)
        ev_1u: float | None = None
        if valid_price(price):
            ev_1u = p_win[idx] * (price - 1.0) - (1.0 - p_win[idx])
        forecasts[rn] = {
            "win_prob": p_win[idx],
            "place_prob": p_place[idx],
            "market_prob": market_prob[idx],
            "value_edge": p_win[idx] - market_prob[idx],
            "ev_1u": ev_1u,
            "certainty": certainty,
        }
    return forecasts


def apply_pro_overlay_to_stake_card(
    stake_card: dict,
    runner_vector_payload: dict,
    forecasts: Dict[int, Dict[str, float | None]],
    *,
    overlay_writer: str = "PRO_OVERLAY_LOGIT_WIN_PLACE_V0",
    tau: float = 0.12,
    feature_flags: Dict[str, bool] | None = None,
) -> dict:
    output = json.loads(json.dumps(stake_card))  # deep copy
    flags = resolve_feature_flags(feature_flags)
    enable_summary = bool(flags.get("enable_runner_narratives"))
    enable_fitness = bool(flags.get("enable_runner_fitness"))
    enable_risk = bool(flags.get("enable_runner_risk"))
    enable_trap_race = bool(flags.get("enable_trap_race"))
    any_insights = enable_summary or enable_fitness or enable_risk
    races = output.get("races", [])
    for race in races:
        for runner in race.get("runners", []):
            rn = runner.get("runner_number")
            if rn in forecasts:
                runner["forecast"] = forecasts[rn]
                if flags.get("ev_bands"):
                    derived = derive_runner_value_fields(runner)
                    runner.update(derived)
            if any_insights:
                insights = derive_runner_insights(
                    runner,
                    enable_summary=enable_summary,
                    enable_fitness=enable_fitness,
                    enable_risk=enable_risk,
                )
                if insights:
                    runner.update(insights)
        if flags.get("race_summary"):
            race["race_summary"] = summarize_race(race)
        if enable_trap_race and derive_trap_race(race, output.get("engine_context", {})):
            race["trap_race"] = True
    ctx = output.setdefault("engine_context", {})
    debug = ctx.setdefault("debug", {})
    debug["overlay_writer"] = overlay_writer
    debug["runner_vector_checksum"] = (runner_vector_payload.get("debug") or {}).get("checksum")
    ctx["forecast_params"] = {
        "tau": tau,
        "alpha": None,
        "tier_prior_policy": "none",
        "market_prob_basis": "valid_prices_only|uniform_if_empty",
        "notes": overlay_writer,
    }
    return output


def build_runner_vector_from_stake_card(stake_card: dict) -> dict:
    ctx = stake_card.get("engine_context", {})
    meeting = stake_card.get("meeting", {})
    race = (stake_card.get("races") or [{}])[0]
    runners = race.get("runners", [])
    engine_inputs = {
        "distance_m": race.get("distance_m"),
        "track_condition_raw": meeting.get("track_condition_raw"),
        "field_size": len(runners),
        "runners": [],
    }
    for runner in runners:
        odds_block = runner.get("odds_minimal") or {}
        engine_inputs["runners"].append(
            {
                "runner_number": runner.get("runner_number"),
                "lite_score": runner.get("lite_score", 0.5),
                "price_now_dec": odds_block.get("price_now_dec"),
                "barrier": runner.get("barrier"),
                "map_role_inferred": runner.get("map_role_inferred"),
                "avg_speed_mps": runner.get("avg_speed_mps"),
                "lite_tag": runner.get("lite_tag"),
            }
        )
    return build_runner_vector(engine_inputs)


def overlay_from_stake_card(stake_card: dict) -> Tuple[dict, Dict[int, Dict[str, float | None]]]:
    runner_vector_payload = build_runner_vector_from_stake_card(stake_card)
    prices = {}
    race = (stake_card.get("races") or [{}])[0]
    for runner in race.get("runners", []):
        rn = runner.get("runner_number")
        odds_block = runner.get("odds_minimal") or {}
        prices[rn] = odds_block.get("price_now_dec")
    forecasts = pro_overlay_logit_win_place_v0(
        runner_vector_payload.get("runners", []),
        prices,
        stake_card.get("engine_context", {}).get("degrade_mode", "NORMAL"),
        stake_card.get("engine_context", {}).get("warnings", []),
    )
    return runner_vector_payload, forecasts
