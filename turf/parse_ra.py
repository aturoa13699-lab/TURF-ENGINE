from __future__ import annotations

"""HTML extraction helpers for Racing Australia style pages.

This is intentionally conservative and deterministic so it can be wired into
automation or GitHub Actions runs without network access. The parser is geared
toward a simple table layout used in tests and can be extended in downstream
workflows to match the real RA DOM.
"""

from dataclasses import dataclass
from typing import List

from selectolax.parser import HTMLParser


@dataclass
class ParsedRunner:
    runner_number: int
    runner_name: str
    barrier: int | None
    price_now_dec: float | None
    map_role_inferred: str | None
    avg_speed_mps: float | None


@dataclass
class ParsedRace:
    meeting_id: str
    race_number: int
    distance_m: int
    runners: List[ParsedRunner]
    captured_at: str


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_meeting_html(
    html: str, *, meeting_id: str, race_number: int, captured_at: str, default_distance_m: int = 1200
) -> ParsedRace:
    """Parse the test-friendly RA HTML into market + speed sidecar inputs.

    The HTML is expected to contain a table with id="runners" where each row
    carries the following attributes:

    - data-runner-number
    - data-runner-name
    - data-barrier (optional)
    - data-price (optional decimal)
    - data-map-role (optional string)
    - data-avg-speed-mps (optional decimal)

    Any missing or unparsable fields are carried through as None so the Lite
    compiler can neutralise deterministically.
    """

    tree = HTMLParser(html)
    table = tree.css_first("table#runners")
    if table is None:
        raise ValueError("No runner table found (table#runners)")

    rows = table.css("tr")
    runners: List[ParsedRunner] = []
    for row in rows:
        attrs = row.attributes
        try:
            runner_number = int(attrs.get("data-runner-number"))
        except (TypeError, ValueError):
            continue

        runner_name = attrs.get("data-runner-name") or f"Runner {runner_number}"
        barrier_val = attrs.get("data-barrier")
        barrier = int(barrier_val) if barrier_val and barrier_val.isdigit() else None
        price = _parse_float(attrs.get("data-price"))
        map_role = attrs.get("data-map-role")
        avg_speed = _parse_float(attrs.get("data-avg-speed-mps"))

        runners.append(
            ParsedRunner(
                runner_number=runner_number,
                runner_name=runner_name,
                barrier=barrier,
                price_now_dec=price,
                map_role_inferred=map_role,
                avg_speed_mps=avg_speed,
            )
        )

    if not runners:
        raise ValueError("No runners found in runner table")

    return ParsedRace(
        meeting_id=meeting_id,
        race_number=race_number,
        distance_m=default_distance_m,
        runners=sorted(runners, key=lambda r: r.runner_number),
        captured_at=captured_at,
    )


def parsed_race_to_market_snapshot(race: ParsedRace) -> dict:
    return {
        "shape_id": "turf.market_snapshot.v1",
        "meeting": {
            "meeting_id": race.meeting_id,
            "track_canonical": race.meeting_id,
            "date_local": race.captured_at.split("T")[0],
        },
        "race": {"race_number": race.race_number, "distance_m": race.distance_m},
        "runners": [
            {
                "runner_number": r.runner_number,
                "runner_name": r.runner_name,
                "barrier": r.barrier,
                "odds_minimal": {"price_now_dec": r.price_now_dec},
            }
            for r in race.runners
        ],
        "provenance": {
            "file_id": race.meeting_id,
            "page_range": "HTML",
            "source_hash": "INLINE",
            "extractor_version": "turf-ra-parser-0.1.0",
            "captured_at": race.captured_at,
        },
    }


def parsed_race_to_speed_sidecar(race: ParsedRace) -> dict:
    return {
        "shape_id": "turf.runner_speed_derived.v1",
        "meeting_id": race.meeting_id,
        "race_number": race.race_number,
        "runners": [
            {
                "runner_number": r.runner_number,
                "avg_speed_mps": r.avg_speed_mps,
                "map_role_inferred": r.map_role_inferred or "UNKNOWN",
            }
            for r in race.runners
        ],
        "provenance": {
            "file_id": race.meeting_id,
            "page_range": "HTML",
            "source_hash": "INLINE",
            "extractor_version": "turf-ra-parser-0.1.0",
            "captured_at": race.captured_at,
        },
    }
