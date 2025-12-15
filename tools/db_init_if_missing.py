from __future__ import annotations

import argparse
from pathlib import Path

try:
    import duckdb  # type: ignore
except ImportError:  # pragma: no cover - fallback for offline CI
    duckdb = None

SCHEMA_FORECASTS = """
CREATE TABLE IF NOT EXISTS forecasts (
  meeting_id TEXT,
  track_canonical TEXT,
  date_local TEXT,
  race_number INTEGER,
  runner_number INTEGER,
  runner_name TEXT,
  lite_score DOUBLE,
  lite_tag TEXT,
  price_now_dec DOUBLE,
  win_prob DOUBLE,
  place_prob DOUBLE,
  market_prob DOUBLE,
  value_edge DOUBLE,
  ev_1u DOUBLE,
  certainty DOUBLE,
  model TEXT,
  captured_at TEXT
);
"""

SCHEMA_RESULTS = """
CREATE TABLE IF NOT EXISTS results (
  meeting_id TEXT,
  race_number INTEGER,
  runner_number INTEGER,
  finish_pos INTEGER,
  sp DOUBLE
);
"""


def init_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if duckdb is None:
        import sqlite3

        conn = sqlite3.connect(db_path)
    else:  # pragma: no cover
        conn = duckdb.connect(str(db_path))
    conn.execute(SCHEMA_FORECASTS)
    conn.execute(SCHEMA_RESULTS)
    return conn


def main() -> None:
    parser = argparse.ArgumentParser(description="Create DuckDB with forecasts/results tables if missing")
    parser.add_argument("--db", type=Path, default=Path("data/turf.duckdb"), help="Path to DuckDB database")
    args = parser.parse_args()
    init_db(args.db)
    print(f"Database ready at {args.db}")


if __name__ == "__main__":
    main()
