from __future__ import annotations

"""Racing Australia (RA) capture and parsing utilities.

This module provides functions to:
- Fetch RA meeting schedule and race HTML pages (via HTTP when available)
- Store raw HTML under deterministic paths: data/raw/ra/<date>/<meeting_id>/race_<n>.html
- Parse stored HTML using existing turf.parse_ra functions
- Operate offline from already-captured files (for tests and CI)

The design is offline-first: parsing always works from captured files,
and network fetching is optional.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from turf.parse_ra import (
    ParsedRace,
    parse_meeting_html,
    parsed_race_to_market_snapshot,
    parsed_race_to_speed_sidecar,
)

# Australia/Sydney timezone for RA date handling
SYDNEY_TZ = ZoneInfo("Australia/Sydney")


@dataclass
class RaceCapture:
    """Metadata for a captured race HTML file."""

    meeting_id: str
    race_number: int
    date_local: str
    html_path: Path
    captured_at: str


@dataclass
class MeetingCapture:
    """Metadata for a captured meeting with all its races."""

    meeting_id: str
    date_local: str
    races: List[RaceCapture]


def _capture_dir_for_meeting(base_dir: Path, date_local: str, meeting_id: str) -> Path:
    """Deterministic path: base_dir/<date>/<meeting_id>/"""
    return base_dir / date_local / meeting_id


def _race_html_path(meeting_dir: Path, race_number: int) -> Path:
    """Deterministic path: meeting_dir/race_<n>.html"""
    return meeting_dir / f"race_{race_number}.html"


def _now_iso(tz: ZoneInfo = SYDNEY_TZ) -> str:
    """Current timestamp in ISO8601 with timezone."""
    return datetime.now(tz).isoformat(timespec="seconds")


def _today_local(tz: ZoneInfo = SYDNEY_TZ) -> str:
    """Today's date in YYYY-MM-DD format for given timezone."""
    return datetime.now(tz).date().isoformat()


def _compute_source_hash(content: str) -> str:
    """Deterministic hash of content for provenance."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Fetching (requires network)
# ---------------------------------------------------------------------------


def _try_import_requests():
    """Import requests lazily to avoid hard dependency."""
    try:
        import requests

        return requests
    except ImportError:
        return None


def fetch_ra_meeting_schedule(
    date_local: str, *, timeout: int = 30, base_url: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]:
    """Fetch RA meeting schedule for a date.

    Returns None if network unavailable or requests not installed.

    The returned list contains meeting stubs with:
    - meeting_id: str
    - track_name: str
    - race_count: int

    In production, this would parse the RA website's meeting schedule page.
    For now, returns None to signal offline operation.
    """
    requests = _try_import_requests()
    if requests is None:
        return None

    # NOTE: Real RA integration would go here. For now, we return None
    # to indicate offline mode. The pipeline will use captured fixtures.
    # This stub is ready for extension when RA API/scraping is implemented.
    return None


def fetch_ra_race_html(
    meeting_id: str,
    race_number: int,
    *,
    timeout: int = 30,
    base_url: Optional[str] = None,
) -> Optional[str]:
    """Fetch raw HTML for a specific race.

    Returns None if network unavailable or requests not installed.
    """
    requests = _try_import_requests()
    if requests is None:
        return None

    # NOTE: Real RA integration would go here.
    return None


# ---------------------------------------------------------------------------
# Capturing (save to disk)
# ---------------------------------------------------------------------------


def capture_race_html(
    html: str,
    meeting_id: str,
    race_number: int,
    date_local: str,
    capture_dir: Path,
    *,
    captured_at: Optional[str] = None,
) -> RaceCapture:
    """Save race HTML to deterministic path and return capture metadata."""
    meeting_dir = _capture_dir_for_meeting(capture_dir, date_local, meeting_id)
    meeting_dir.mkdir(parents=True, exist_ok=True)

    html_path = _race_html_path(meeting_dir, race_number)
    html_path.write_text(html)

    cap_time = captured_at or _now_iso()
    return RaceCapture(
        meeting_id=meeting_id,
        race_number=race_number,
        date_local=date_local,
        html_path=html_path,
        captured_at=cap_time,
    )


def capture_meeting(
    meeting_id: str,
    date_local: str,
    race_htmls: Dict[int, str],
    capture_dir: Path,
    *,
    captured_at: Optional[str] = None,
) -> MeetingCapture:
    """Capture all race HTMLs for a meeting."""
    cap_time = captured_at or _now_iso()
    races = []
    for race_number in sorted(race_htmls.keys()):
        html = race_htmls[race_number]
        race_cap = capture_race_html(
            html, meeting_id, race_number, date_local, capture_dir, captured_at=cap_time
        )
        races.append(race_cap)

    return MeetingCapture(meeting_id=meeting_id, date_local=date_local, races=races)


# ---------------------------------------------------------------------------
# Loading (from disk)
# ---------------------------------------------------------------------------


def load_captured_race(
    capture_dir: Path, date_local: str, meeting_id: str, race_number: int
) -> Optional[RaceCapture]:
    """Load a captured race HTML file if it exists."""
    meeting_dir = _capture_dir_for_meeting(capture_dir, date_local, meeting_id)
    html_path = _race_html_path(meeting_dir, race_number)

    if not html_path.exists():
        return None

    return RaceCapture(
        meeting_id=meeting_id,
        race_number=race_number,
        date_local=date_local,
        html_path=html_path,
        captured_at="UNKNOWN",  # Could read from metadata file
    )


def load_captured_meeting(
    capture_dir: Path, date_local: str, meeting_id: str
) -> Optional[MeetingCapture]:
    """Load all captured race HTMLs for a meeting."""
    meeting_dir = _capture_dir_for_meeting(capture_dir, date_local, meeting_id)

    if not meeting_dir.exists():
        return None

    races = []
    for html_path in sorted(meeting_dir.glob("race_*.html")):
        # Extract race number from filename
        try:
            race_str = html_path.stem.replace("race_", "")
            race_number = int(race_str)
        except ValueError:
            continue

        races.append(
            RaceCapture(
                meeting_id=meeting_id,
                race_number=race_number,
                date_local=date_local,
                html_path=html_path,
                captured_at="UNKNOWN",
            )
        )

    if not races:
        return None

    return MeetingCapture(meeting_id=meeting_id, date_local=date_local, races=races)


def discover_captured_meetings(capture_dir: Path, date_local: str) -> List[str]:
    """Discover all meeting IDs that have been captured for a date."""
    date_dir = capture_dir / date_local
    if not date_dir.exists():
        return []

    meeting_ids = []
    for subdir in sorted(date_dir.iterdir()):
        if subdir.is_dir() and any(subdir.glob("race_*.html")):
            meeting_ids.append(subdir.name)

    return meeting_ids


# ---------------------------------------------------------------------------
# Parsing (from captured files)
# ---------------------------------------------------------------------------


def parse_captured_race(
    capture: RaceCapture, *, default_distance_m: int = 1200
) -> ParsedRace:
    """Parse a captured race HTML file into a ParsedRace."""
    html = capture.html_path.read_text()
    captured_at = f"{capture.date_local}T10:00:00+11:00"  # Default AEDT

    return parse_meeting_html(
        html,
        meeting_id=capture.meeting_id,
        race_number=capture.race_number,
        captured_at=captured_at,
        default_distance_m=default_distance_m,
    )


def parse_captured_meeting(
    capture: MeetingCapture, *, default_distance_m: int = 1200
) -> List[ParsedRace]:
    """Parse all races in a captured meeting."""
    return [
        parse_captured_race(race, default_distance_m=default_distance_m)
        for race in capture.races
    ]


def captured_race_to_artifacts(
    capture: RaceCapture, *, default_distance_m: int = 1200
) -> tuple[dict, dict]:
    """Parse a captured race and return (market_snapshot, speed_sidecar) dicts."""
    parsed = parse_captured_race(capture, default_distance_m=default_distance_m)
    market = parsed_race_to_market_snapshot(parsed)
    sidecar = parsed_race_to_speed_sidecar(parsed)

    # Add source hash from captured HTML
    html_content = capture.html_path.read_text()
    source_hash = _compute_source_hash(html_content)
    market["provenance"]["source_hash"] = source_hash
    sidecar["provenance"]["source_hash"] = source_hash

    return market, sidecar


def captured_meeting_to_artifacts(
    capture: MeetingCapture, *, default_distance_m: int = 1200
) -> List[tuple[dict, dict]]:
    """Parse all races in a captured meeting and return list of (market, sidecar) tuples."""
    return [
        captured_race_to_artifacts(race, default_distance_m=default_distance_m)
        for race in capture.races
    ]
