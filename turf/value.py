"""Deterministic value/EV helpers for PRO outputs and CLI rendering."""

from __future__ import annotations

from typing import Dict, Optional


def ev_band(ev: Optional[float]) -> Optional[str]:
    if ev is None:
        return None
    if ev >= 0.25:
        return "A"
    if ev >= 0.10:
        return "B"
    if ev >= 0.0:
        return "C"
    if ev >= -0.05:
        return "D"
    return "E"


def ev_marker(value_edge: Optional[float]) -> Optional[str]:
    if value_edge is None:
        return None
    if value_edge >= 0.05:
        return "🟢"
    if value_edge <= -0.05:
        return "🔴"
    return "⚪️"


def confidence_class(certainty: Optional[float]) -> Optional[str]:
    if certainty is None:
        return None
    if certainty >= 0.90:
        return "HIGH"
    if certainty >= 0.75:
        return "MEDIUM"
    return "LOW"


def risk_profile(win_prob: Optional[float], price: Optional[float]) -> Optional[str]:
    if win_prob is None or price is None or price <= 1.0:
        return None
    implied = 1.0 / price
    delta = win_prob - implied
    if delta >= 0.05:
        return "VALUE"
    if delta <= -0.05:
        return "UNDERLAY"
    return "FAIR"


def model_vs_market_alert(value_edge: Optional[float]) -> Optional[str]:
    if value_edge is None:
        return None
    if value_edge >= 0.08:
        return "overlay_positive"
    if value_edge <= -0.08:
        return "overlay_negative"
    return None


def derive_runner_value_fields(runner: Dict[str, object]) -> Dict[str, object]:
    forecast = (runner.get("forecast") or {}) if isinstance(runner, dict) else {}
    odds_block = runner.get("odds_minimal") if isinstance(runner, dict) else None
    price = None
    if isinstance(odds_block, dict):
        price = odds_block.get("price_now_dec")

    win_prob = forecast.get("win_prob") if isinstance(forecast, dict) else None
    value_edge = forecast.get("value_edge") if isinstance(forecast, dict) else None
    ev_val = forecast.get("ev_1u") if isinstance(forecast, dict) else None
    certainty = forecast.get("certainty") if isinstance(forecast, dict) else None

    return {
        "ev": ev_val,
        "ev_band": ev_band(ev_val),
        "ev_marker": ev_marker(value_edge),
        "confidence_class": confidence_class(certainty),
        "risk_profile": risk_profile(win_prob, price),
        "model_vs_market_alert": model_vs_market_alert(value_edge),
    }
