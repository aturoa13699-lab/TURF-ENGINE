from __future__ import annotations

"""Generic odds parser for simple HTML tables.

This module targets the test fixtures included in the repo. Downstream users can
extend the parser to match provider-specific DOMs while keeping deterministic
output for the Lite compiler.
"""

from dataclasses import dataclass
from selectolax.parser import HTMLParser


@dataclass
class ParsedOddsRow:
    runner_name: str
    price_now_dec: float | None


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_generic_odds_table(html: str) -> list[ParsedOddsRow]:
    tree = HTMLParser(html)
    table = tree.css_first("table#odds")
    if table is None:
        raise ValueError("No odds table found (table#odds)")

    rows: list[ParsedOddsRow] = []
    for row in table.css("tr"):
        attrs = row.attributes
        name = attrs.get("data-runner-name")
        if not name:
            continue
        price = _parse_float(attrs.get("data-price"))
        rows.append(ParsedOddsRow(runner_name=name, price_now_dec=price))

    if not rows:
        raise ValueError("No odds rows parsed")
    return rows


def parsed_odds_to_market(rows: list[ParsedOddsRow], meeting_id: str, race_number: int, captured_at: str) -> dict:
    return {
        "shape_id": "turf.market_odds.v1",
        "meeting_id": meeting_id,
        "race_number": race_number,
        "captured_at": captured_at,
        "runners": [
            {"runner_name": row.runner_name, "price_now_dec": row.price_now_dec}
            for row in rows
        ],
    }
