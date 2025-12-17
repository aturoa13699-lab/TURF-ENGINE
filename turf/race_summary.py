"""Race-level summaries derived from PRO overlay fields."""

from __future__ import annotations

from typing import Dict, List, Optional

from turf.value import derive_runner_value_fields


def _safe_num(value: Optional[float]) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def summarize_race(race: dict) -> Dict[str, object]:
    runners = race.get("runners", []) if isinstance(race, dict) else []
    enriched = []
    for runner in runners:
        if not isinstance(runner, dict):
            continue
        forecast = runner.get("forecast") or {}
        value_fields = derive_runner_value_fields(runner)
        enriched.append(
            {
                "runner_number": runner.get("runner_number"),
                "forecast": forecast,
                "value": value_fields,
                "price": (runner.get("odds_minimal") or {}).get("price_now_dec"),
                "name": runner.get("runner_name", ""),
            }
        )

    top_sorted = sorted(
        enriched,
        key=lambda r: (
            -_safe_num((r.get("forecast") or {}).get("win_prob")),
            -_safe_num((r.get("value") or {}).get("ev")),
            r.get("runner_number") or 0,
        ),
    )
    top_picks = [r.get("runner_number") for r in top_sorted[:2] if r.get("runner_number")]

    value_sorted = [r for r in enriched if (r.get("value") or {}).get("ev") is not None]
    value_sorted = sorted(value_sorted, key=lambda r: (-_safe_num((r.get("value") or {}).get("ev")), r.get("runner_number") or 0))
    value_picks = [r.get("runner_number") for r in value_sorted if _safe_num((r.get("value") or {}).get("ev")) > 0][:2]

    fades_sorted = sorted(
        [r for r in value_sorted if _safe_num((r.get("value") or {}).get("ev")) < -0.01],
        key=lambda r: (_safe_num((r.get("value") or {}).get("ev")), r.get("runner_number") or 0),
    )
    fades = [r.get("runner_number") for r in fades_sorted[:2]]

    trap_race = len(value_picks) == 0

    strategy_parts: List[str] = []
    if top_picks:
        strategy_parts.append(f"Win: {', '.join(map(str, top_picks))}")
    if value_picks:
        strategy_parts.append(f"Value: {', '.join(map(str, value_picks))}")
    if fades:
        strategy_parts.append(f"Fades: {', '.join(map(str, fades))}")
    strategy = "; ".join(strategy_parts) if strategy_parts else "Observe only"

    return {
        "top_picks": top_picks,
        "value_picks": value_picks,
        "fades": fades,
        "trap_race": trap_race,
        "strategy": strategy,
    }
