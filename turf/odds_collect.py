from __future__ import annotations

"""Pluggable odds collection adapters for various sources.

Supported sources:
- theoddsapi: The Odds API (requires API key)
- betfair: Betfair Exchange API (requires credentials)
- none: No odds fetching (use existing prices from RA data)
- fixture: Load from fixture files (for testing)

All adapters return odds in the minimal format expected by merge_odds_into_market:
{
    "runners": [
        {"runner_name": "...", "price_now_dec": ...},
        ...
    ]
}

Captured odds are stored under deterministic paths:
data/raw/<source>/<date>/<meeting_id>/race_<n>.json
"""

import hashlib
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

SYDNEY_TZ = ZoneInfo("Australia/Sydney")


@dataclass
class OddsSnapshot:
    """Captured odds for a single race."""

    meeting_id: str
    race_number: int
    date_local: str
    source: str
    runners: List[Dict[str, Any]]
    captured_at: str
    raw_path: Optional[Path] = None


def _now_iso(tz: ZoneInfo = SYDNEY_TZ) -> str:
    """Current timestamp in ISO8601 with timezone."""
    return datetime.now(tz).isoformat(timespec="seconds")


def _compute_hash(content: str) -> str:
    """Deterministic hash for provenance."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _capture_dir_for_source(
    base_dir: Path, source: str, date_local: str, meeting_id: str
) -> Path:
    """Deterministic path: base_dir/<source>/<date>/<meeting_id>/"""
    return base_dir / source / date_local / meeting_id


def _odds_json_path(meeting_dir: Path, race_number: int) -> Path:
    """Deterministic path: meeting_dir/race_<n>.json"""
    return meeting_dir / f"race_{race_number}.json"


# ---------------------------------------------------------------------------
# Base adapter interface
# ---------------------------------------------------------------------------


class OddsAdapter(ABC):
    """Base class for odds source adapters."""

    source_name: str = "unknown"

    @abstractmethod
    def fetch_odds(
        self,
        meeting_id: str,
        race_number: int,
        date_local: str,
        *,
        runner_names: Optional[List[str]] = None,
    ) -> Optional[OddsSnapshot]:
        """Fetch odds for a specific race.

        Args:
            meeting_id: Meeting identifier (e.g., track name)
            race_number: Race number (1-indexed)
            date_local: Date in YYYY-MM-DD format
            runner_names: Optional list of runner names for matching

        Returns:
            OddsSnapshot with runner prices, or None if unavailable
        """
        pass

    def fetch_meeting_odds(
        self,
        meeting_id: str,
        race_numbers: List[int],
        date_local: str,
        *,
        runner_names_by_race: Optional[Dict[int, List[str]]] = None,
    ) -> Dict[int, OddsSnapshot]:
        """Fetch odds for all races in a meeting.

        Returns a dict mapping race_number to OddsSnapshot.
        """
        results = {}
        for race_num in race_numbers:
            runner_names = None
            if runner_names_by_race:
                runner_names = runner_names_by_race.get(race_num)
            snapshot = self.fetch_odds(
                meeting_id, race_num, date_local, runner_names=runner_names
            )
            if snapshot:
                results[race_num] = snapshot
        return results


# ---------------------------------------------------------------------------
# No-op adapter (use RA prices)
# ---------------------------------------------------------------------------


class NoneAdapter(OddsAdapter):
    """Adapter that returns no odds (use prices from RA data)."""

    source_name = "none"

    def fetch_odds(
        self,
        meeting_id: str,
        race_number: int,
        date_local: str,
        *,
        runner_names: Optional[List[str]] = None,
    ) -> Optional[OddsSnapshot]:
        return None


# ---------------------------------------------------------------------------
# Fixture adapter (for testing)
# ---------------------------------------------------------------------------


class FixtureAdapter(OddsAdapter):
    """Adapter that loads odds from fixture files."""

    source_name = "fixture"

    def __init__(self, fixtures_dir: Path):
        self.fixtures_dir = fixtures_dir

    def fetch_odds(
        self,
        meeting_id: str,
        race_number: int,
        date_local: str,
        *,
        runner_names: Optional[List[str]] = None,
    ) -> Optional[OddsSnapshot]:
        # Look for fixture at fixtures_dir/<date>/<meeting_id>/race_<n>.json
        # or fixtures_dir/<meeting_id>/race_<n>.json
        # or fixtures_dir/race_<n>.json
        candidates = [
            self.fixtures_dir / date_local / meeting_id / f"race_{race_number}.json",
            self.fixtures_dir / meeting_id / f"race_{race_number}.json",
            self.fixtures_dir / f"race_{race_number}.json",
            self.fixtures_dir / "odds.json",  # Single fixture fallback
        ]

        for path in candidates:
            if path.exists():
                return self._load_fixture(
                    path, meeting_id, race_number, date_local
                )

        return None

    def _load_fixture(
        self, path: Path, meeting_id: str, race_number: int, date_local: str
    ) -> OddsSnapshot:
        data = json.loads(path.read_text())

        # Support both raw runner list and wrapped format
        if "runners" in data:
            runners = data["runners"]
        else:
            runners = data if isinstance(data, list) else []

        return OddsSnapshot(
            meeting_id=meeting_id,
            race_number=race_number,
            date_local=date_local,
            source="fixture",
            runners=runners,
            captured_at=data.get("captured_at", _now_iso()),
            raw_path=path,
        )


# ---------------------------------------------------------------------------
# The Odds API adapter
# ---------------------------------------------------------------------------


class TheOddsAPIAdapter(OddsAdapter):
    """Adapter for The Odds API.

    Requires environment variable:
    - THEODDSAPI_KEY: API key for The Odds API

    Note: The Odds API uses different event identification than RA.
    This adapter attempts to match by track name and date.
    """

    source_name = "theoddsapi"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("THEODDSAPI_KEY")
        self._requests = None

    def _get_requests(self):
        if self._requests is None:
            try:
                import requests

                self._requests = requests
            except ImportError:
                return None
        return self._requests

    def fetch_odds(
        self,
        meeting_id: str,
        race_number: int,
        date_local: str,
        *,
        runner_names: Optional[List[str]] = None,
    ) -> Optional[OddsSnapshot]:
        if not self.api_key:
            return None

        requests = self._get_requests()
        if requests is None:
            return None

        # NOTE: Real implementation would call The Odds API here.
        # The API uses sport keys like "horse_racing" and requires
        # event lookup by date/track. For now, return None to signal
        # offline mode. The pipeline will fall back to RA prices.
        #
        # When implementing:
        # 1. GET /v4/sports/horse_racing_aus/odds?regions=au&markets=h2h
        # 2. Filter events by commence_time matching date_local
        # 3. Match track name (meeting_id) to event
        # 4. Extract bookmaker odds and convert to price_now_dec

        return None


# ---------------------------------------------------------------------------
# Betfair adapter
# ---------------------------------------------------------------------------


class BetfairAdapter(OddsAdapter):
    """Adapter for Betfair Exchange API.

    Requires environment variables:
    - BETFAIR_APP_KEY: Betfair application key
    - BETFAIR_USERNAME: Betfair username
    - BETFAIR_PASSWORD: Betfair password
    OR
    - BETFAIR_SESSION_TOKEN: Pre-authenticated session token

    Note: Betfair uses market IDs for identification. This adapter
    requires a mapping from RA meeting/race to Betfair market IDs.
    """

    source_name = "betfair"

    def __init__(
        self,
        app_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        session_token: Optional[str] = None,
    ):
        self.app_key = app_key or os.environ.get("BETFAIR_APP_KEY")
        self.username = username or os.environ.get("BETFAIR_USERNAME")
        self.password = password or os.environ.get("BETFAIR_PASSWORD")
        self.session_token = session_token or os.environ.get("BETFAIR_SESSION_TOKEN")
        self._requests = None

    def _get_requests(self):
        if self._requests is None:
            try:
                import requests

                self._requests = requests
            except ImportError:
                return None
        return self._requests

    def fetch_odds(
        self,
        meeting_id: str,
        race_number: int,
        date_local: str,
        *,
        runner_names: Optional[List[str]] = None,
    ) -> Optional[OddsSnapshot]:
        if not self.app_key:
            return None

        requests = self._get_requests()
        if requests is None:
            return None

        # NOTE: Real implementation would:
        # 1. Authenticate with Betfair if no session token
        # 2. Call listEvents to find horse racing events for date
        # 3. Match venue name to meeting_id
        # 4. Call listMarketCatalogue to get market IDs for races
        # 5. Call listMarketBook to get current prices
        # 6. Convert selection prices to runner odds
        #
        # This is left as a stub for future implementation.
        # The pipeline will fall back to RA prices.

        return None


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


def get_odds_adapter(
    source: str, *, fixtures_dir: Optional[Path] = None, **kwargs
) -> OddsAdapter:
    """Get an odds adapter by source name.

    Args:
        source: One of "none", "fixture", "theoddsapi", "betfair"
        fixtures_dir: Required for "fixture" source
        **kwargs: Additional adapter-specific configuration

    Returns:
        Configured OddsAdapter instance
    """
    source_lower = source.lower()

    if source_lower == "none":
        return NoneAdapter()
    elif source_lower == "fixture":
        if fixtures_dir is None:
            raise ValueError("fixtures_dir required for fixture adapter")
        return FixtureAdapter(fixtures_dir)
    elif source_lower == "theoddsapi":
        return TheOddsAPIAdapter(api_key=kwargs.get("api_key"))
    elif source_lower == "betfair":
        return BetfairAdapter(
            app_key=kwargs.get("app_key"),
            username=kwargs.get("username"),
            password=kwargs.get("password"),
            session_token=kwargs.get("session_token"),
        )
    else:
        raise ValueError(f"Unknown odds source: {source}")


# ---------------------------------------------------------------------------
# Capture and load utilities
# ---------------------------------------------------------------------------


def capture_odds_snapshot(
    snapshot: OddsSnapshot, capture_dir: Path
) -> Path:
    """Save odds snapshot to deterministic path."""
    meeting_dir = _capture_dir_for_source(
        capture_dir, snapshot.source, snapshot.date_local, snapshot.meeting_id
    )
    meeting_dir.mkdir(parents=True, exist_ok=True)

    json_path = _odds_json_path(meeting_dir, snapshot.race_number)
    payload = {
        "meeting_id": snapshot.meeting_id,
        "race_number": snapshot.race_number,
        "date_local": snapshot.date_local,
        "source": snapshot.source,
        "runners": snapshot.runners,
        "captured_at": snapshot.captured_at,
    }
    json_path.write_text(json.dumps(payload, indent=2))
    return json_path


def load_captured_odds(
    capture_dir: Path,
    source: str,
    date_local: str,
    meeting_id: str,
    race_number: int,
) -> Optional[OddsSnapshot]:
    """Load captured odds snapshot if it exists."""
    meeting_dir = _capture_dir_for_source(capture_dir, source, date_local, meeting_id)
    json_path = _odds_json_path(meeting_dir, race_number)

    if not json_path.exists():
        return None

    data = json.loads(json_path.read_text())
    return OddsSnapshot(
        meeting_id=data["meeting_id"],
        race_number=data["race_number"],
        date_local=data["date_local"],
        source=data["source"],
        runners=data["runners"],
        captured_at=data["captured_at"],
        raw_path=json_path,
    )


# ---------------------------------------------------------------------------
# Conversion to merge format
# ---------------------------------------------------------------------------


def odds_snapshot_to_merge_format(snapshot: OddsSnapshot) -> dict:
    """Convert OddsSnapshot to format expected by merge_odds_into_market.

    The merge function expects:
    {
        "runners": [
            {"runner_name": "...", "price_now_dec": ...},
            ...
        ]
    }
    """
    runners = []
    for r in snapshot.runners:
        # Support various input formats
        name = r.get("runner_name") or r.get("name") or r.get("selection_name")
        price = r.get("price_now_dec") or r.get("price") or r.get("odds")

        if name and price is not None:
            try:
                price_float = float(price)
                runners.append({"runner_name": name, "price_now_dec": price_float})
            except (TypeError, ValueError):
                continue

    return {"runners": runners}


def odds_snapshot_to_runner_number_map(
    snapshot: OddsSnapshot,
) -> Dict[int, float]:
    """Convert OddsSnapshot to runner_number -> price_now_dec mapping.

    Useful when odds are keyed by runner number rather than name.
    """
    result = {}
    for r in snapshot.runners:
        runner_num = r.get("runner_number")
        price = r.get("price_now_dec") or r.get("price") or r.get("odds")

        if runner_num is not None and price is not None:
            try:
                result[int(runner_num)] = float(price)
            except (TypeError, ValueError):
                continue

    return result
