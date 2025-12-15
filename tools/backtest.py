from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Optional

from tools.db_init_if_missing import init_db


METRIC_OUTPUT = {
    "count": 0,
    "brier": None,
    "logloss": None,
    "roi": None,
    "roi_sample_size": 0,
}


def _safe_logloss(win_prob: float, outcome: int, eps: float = 1e-12) -> float:
    p = min(max(win_prob, eps), 1 - eps)
    return -(outcome * math.log(p) + (1 - outcome) * math.log(1 - p))


def run_backtest(db_path: Path, *, model: str, start: Optional[str], end: Optional[str], out_dir: Path) -> Dict[str, float | int | None]:
    conn = init_db(db_path)
    where = "model = ?"
    params = [model]
    if start:
        where += " AND date_local >= ?"
        params.append(start)
    if end:
        where += " AND date_local <= ?"
        params.append(end)

    rows = conn.execute(
        f"SELECT meeting_id, race_number, runner_number, price_now_dec, win_prob, value_edge FROM forecasts WHERE {where}", params
    ).fetchall()
    if not rows:
        return METRIC_OUTPUT.copy()

    results = conn.execute(
        "SELECT meeting_id, race_number, runner_number, finish_pos, sp FROM results"
    ).fetchall()
    results_map = {(m, r, rn): (pos, sp) for m, r, rn, pos, sp in results}

    total = 0
    brier_sum = 0.0
    logloss_sum = 0.0
    roi_sum = 0.0
    roi_count = 0

    for meeting_id, race_number, runner_number, price_now_dec, win_prob, value_edge in rows:
        key = (meeting_id, race_number, runner_number)
        outcome = 1 if results_map.get(key, (None, None))[0] == 1 else 0
        if win_prob is None:
            continue
        total += 1
        brier_sum += (win_prob - outcome) ** 2
        logloss_sum += _safe_logloss(win_prob, outcome)
        if value_edge is not None and value_edge > 0.02 and price_now_dec:
            ev = (price_now_dec - 1.0) if outcome else -1.0
            roi_sum += ev
            roi_count += 1

    metrics = {
        "count": total,
        "brier": brier_sum / total if total else None,
        "logloss": logloss_sum / total if total else None,
        "roi": roi_sum / roi_count if roi_count else None,
        "roi_sample_size": roi_count,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "backtest_metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run simple backtest over stored forecasts")
    parser.add_argument("--db", type=Path, default=Path("data/turf.duckdb"))
    parser.add_argument("--model", type=str, default="LOGIT_WIN_PLACE_V0")
    parser.add_argument("--start", type=str, default=None, help="Optional start date inclusive")
    parser.add_argument("--end", type=str, default=None, help="Optional end date inclusive")
    parser.add_argument("--out", type=Path, default=Path("out/reports"))
    args = parser.parse_args()
    metrics = run_backtest(args.db, model=args.model, start=args.start, end=args.end, out_dir=args.out)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
