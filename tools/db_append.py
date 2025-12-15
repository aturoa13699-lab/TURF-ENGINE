from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, List

from tools.db_init_if_missing import init_db


def load_stake_cards(stake_dir: Path) -> List[dict]:
    payloads: List[dict] = []
    for path in sorted(stake_dir.glob("*.json")):
        payloads.append(json.loads(path.read_text()))
    return payloads


def rows_from_stake_card(card: dict, model: str) -> Iterable[tuple]:
    ctx = card.get("engine_context", {})
    meeting = card.get("meeting", {})
    for race in card.get("races", []):
        for runner in race.get("runners", []):
            forecast = runner.get("forecast") or {}
            odds_block = runner.get("odds_minimal") or {}
            yield (
                meeting.get("meeting_id"),
                meeting.get("track_canonical"),
                meeting.get("date_local"),
                race.get("race_number"),
                runner.get("runner_number"),
                runner.get("runner_name"),
                runner.get("lite_score"),
                runner.get("lite_tag"),
                odds_block.get("price_now_dec"),
                forecast.get("win_prob"),
                forecast.get("place_prob"),
                forecast.get("market_prob"),
                forecast.get("value_edge"),
                forecast.get("ev_1u"),
                forecast.get("certainty"),
                model,
                ctx.get("snapshot_ts") or ctx.get("captured_at") or "",
            )


def append_cards(db_path: Path, stake_dir: Path, *, model: str = "LOGIT_WIN_PLACE_V0") -> int:
    conn = init_db(db_path)
    rows = []
    for card in load_stake_cards(stake_dir):
        rows.extend(list(rows_from_stake_card(card, model)))
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO forecasts (
            meeting_id, track_canonical, date_local, race_number, runner_number,
            runner_name, lite_score, lite_tag, price_now_dec, win_prob, place_prob,
            market_prob, value_edge, ev_1u, certainty, model, captured_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    if hasattr(conn, "commit"):
        conn.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Append stake card forecasts into DuckDB")
    parser.add_argument("--db", type=Path, default=Path("data/turf.duckdb"), help="DuckDB path")
    parser.add_argument("--cards", type=Path, default=Path("out/cards"), help="Directory containing stake card JSON files")
    parser.add_argument("--model", type=str, default="LOGIT_WIN_PLACE_V0", help="Model identifier")
    args = parser.parse_args()
    inserted = append_cards(args.db, args.cards, model=args.model)
    print(f"Inserted {inserted} forecast rows into {args.db}")


if __name__ == "__main__":
    main()
