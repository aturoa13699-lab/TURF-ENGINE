from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _safe_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        return int(x)
    except (TypeError, ValueError):
        return None


def _implied_prob(price_dec: Optional[float]) -> Optional[float]:
    if price_dec is None or price_dec <= 1.0:
        return None
    return 1.0 / price_dec


def _risk_profile(win_prob: Optional[float], price_dec: Optional[float]) -> Optional[str]:
    if win_prob is None or price_dec is None or price_dec <= 1.0:
        return None
    implied = _implied_prob(price_dec)
    if implied is None:
        return None
    delta = win_prob - implied
    if delta >= 0.05:
        return "VALUE"
    if delta <= -0.05:
        return "UNDERLAY"
    return "FAIR"


def derive_runner_insights(
    runner: Dict[str, Any],
    *,
    enable_summary: bool,
    enable_fitness: bool,
    enable_risk: bool,
) -> Dict[str, Any]:
    """
    Plan 060: deterministic runner narratives / fitness / risk.
    Pure: MUST NOT mutate runner.
    """
    out: Dict[str, Any] = {}

    barrier = _safe_int(runner.get("barrier"))
    map_role = runner.get("map_role_inferred") or runner.get("map_role") or runner.get("role")
    map_role = str(map_role).upper() if map_role is not None else None

    price_dec = _safe_float(runner.get("price_now_dec"))
    if price_dec is None:
        odds_min = runner.get("odds_minimal") or {}
        if isinstance(odds_min, dict):
            price_dec = _safe_float(odds_min.get("price_now_dec"))

    forecast = runner.get("forecast") or {}
    win_prob = None
    certainty = None
    if isinstance(forecast, dict):
        win_prob = _safe_float(forecast.get("win_prob"))
        certainty = _safe_float(forecast.get("certainty"))

    fitness_flags: List[str] = []
    if enable_fitness:
        if barrier is not None:
            if barrier <= 3:
                fitness_flags.append("GOOD_BARRIER")
            elif barrier >= 10:
                fitness_flags.append("WIDE_BARRIER")

        if map_role in ("LEAD", "LEADER"):
            fitness_flags.append("LIKELY_LEADER")
        elif map_role in ("ON_PACE", "ONPACE"):
            fitness_flags.append("ON_PACE_PATTERN")

        days = _safe_int(runner.get("days_since_run"))
        if days is not None:
            if days <= 21:
                fitness_flags.append("RECENT_RUN")
            elif days >= 60:
                fitness_flags.append("LONG_BREAK")

        avg_speed = _safe_float(runner.get("avg_speed_mps"))
        if avg_speed is not None and avg_speed >= 17.5:
            fitness_flags.append("HIGH_SPEED")

        fitness_flags = sorted(set(fitness_flags))
        if fitness_flags:
            out["fitness_flags"] = fitness_flags

    risk_tags: List[str] = []
    risk_profile = None
    if enable_risk:
        risk_profile = _risk_profile(win_prob, price_dec)
        if risk_profile:
            risk_tags.append(risk_profile)

        if certainty is not None and certainty < 0.70:
            risk_tags.append("LOW_CERTAINTY")

        if price_dec is not None and price_dec >= 15.0:
            risk_tags.append("LONGSHOT")

        risk_tags = sorted(set(risk_tags))
        if risk_tags:
            out["risk_tags"] = risk_tags
        if risk_profile:
            out["risk_profile"] = risk_profile

    if enable_summary:
        parts: List[str] = []
        if map_role in ("LEAD", "LEADER"):
            parts.append("Likely leader pattern")
        elif map_role in ("ON_PACE", "ONPACE"):
            parts.append("On-pace pattern")
        elif map_role in ("MID", "MIDFIELD"):
            parts.append("Midfield pattern")
        elif map_role in ("BACK", "GET_BACK"):
            parts.append("Get-back pattern")

        if barrier is not None:
            if barrier <= 3:
                parts.append(f"inside draw (barrier {barrier})")
            elif barrier >= 10:
                parts.append(f"wide draw (barrier {barrier})")
            else:
                parts.append(f"barrier {barrier}")

        if risk_profile:
            parts.append(f"risk_profile={risk_profile}")

        if win_prob is not None:
            parts.append(f"win_prob={win_prob:.2f}")

        if parts:
            out["summary"] = "; ".join(parts) + "."

    return out


def derive_trap_race(race: Dict[str, Any], engine_context: Dict[str, Any]) -> bool:
    """
    Plan 060: deterministic trap_race indicator (race-level).
    """
    degrade_mode = str(engine_context.get("degrade_mode") or "").upper()
    warnings = engine_context.get("warnings") or []
    if degrade_mode and degrade_mode != "NORMAL":
        return True
    if isinstance(warnings, list) and len(warnings) > 0:
        return True

    runners = race.get("runners") or []
    if not isinstance(runners, list) or not runners:
        return False

    n = len(runners)
    back = inside = wide = missing_price = 0

    low = 0
    seen = 0
    for r in runners:
        if not isinstance(r, dict):
            continue
        fc = r.get("forecast")
        if isinstance(fc, dict):
            c = _safe_float(fc.get("certainty"))
            if c is not None:
                seen += 1
                if c < 0.70:
                    low += 1

        role = r.get("map_role_inferred") or r.get("map_role") or r.get("role")
        role = str(role).upper() if role is not None else None
        if role and "BACK" in role:
            back += 1

        b = _safe_int(r.get("barrier"))
        if b is not None and b <= 2:
            inside += 1
        if b is not None and b >= 10:
            wide += 1

        odds = r.get("odds_minimal") or {}
        if isinstance(odds, dict):
            if _safe_float(odds.get("price_now_dec")) is None:
                missing_price += 1

    if seen > 0 and (low / float(seen)) >= 0.50:
        return True
    if n >= 10 and back >= max(3, n // 3):
        return True
    if n >= 12 and inside >= 2 and wide >= 2:
        return True
    if missing_price >= max(3, n // 3):
        return True
    return False
