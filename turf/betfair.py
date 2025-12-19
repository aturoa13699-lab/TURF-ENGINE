from __future__ import annotations

"""Betfair Exchange API adapter with certificate-based authentication.

This module provides:
- Certificate-based login (non-interactive SSO)
- Market discovery for Australian horse racing
- Odds retrieval with deterministic runner name matching

Required environment variables (or GitHub Secrets):
- BETFAIR_APP_KEY: Betfair application key (X-Application header)
- BETFAIR_USERNAME: Betfair account username
- BETFAIR_PASSWORD: Betfair account password
- BETFAIR_CERT_PEM_B64: Base64-encoded PEM certificate (.crt)
- BETFAIR_KEY_PEM_B64: Base64-encoded PEM private key (.key)

The adapter writes cert/key to ~/.betfair/ at runtime.
"""

import base64
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

SYDNEY_TZ = ZoneInfo("Australia/Sydney")

# Betfair API endpoints
BETFAIR_CERT_LOGIN_URL = "https://identitysso-cert.betfair.com/api/certlogin"
BETFAIR_EXCHANGE_URL = "https://api.betfair.com/exchange/betting/rest/v1.0"

# Horse racing event type ID
HORSE_RACING_EVENT_TYPE_ID = "7"


class BetfairAuthError(Exception):
    """Raised when Betfair authentication fails."""

    pass


class BetfairConfigError(Exception):
    """Raised when required Betfair configuration is missing."""

    pass


@dataclass
class BetfairConfig:
    """Configuration for Betfair API access."""

    app_key: str
    username: str
    password: str
    cert_pem: str  # PEM content (decoded)
    key_pem: str  # PEM content (decoded)

    @classmethod
    def from_env(cls) -> "BetfairConfig":
        """Load config from environment variables.

        Raises BetfairConfigError with clear message if secrets are missing.
        """
        missing = []

        app_key = os.environ.get("BETFAIR_APP_KEY")
        if not app_key:
            missing.append("BETFAIR_APP_KEY")

        username = os.environ.get("BETFAIR_USERNAME")
        if not username:
            missing.append("BETFAIR_USERNAME")

        password = os.environ.get("BETFAIR_PASSWORD")
        if not password:
            missing.append("BETFAIR_PASSWORD")

        cert_b64 = os.environ.get("BETFAIR_CERT_PEM_B64")
        if not cert_b64:
            missing.append("BETFAIR_CERT_PEM_B64")

        key_b64 = os.environ.get("BETFAIR_KEY_PEM_B64")
        if not key_b64:
            missing.append("BETFAIR_KEY_PEM_B64")

        if missing:
            raise BetfairConfigError(
                f"Missing required Betfair secrets: {', '.join(missing)}. "
                "Please configure these as GitHub Secrets or environment variables. "
                "See docs/plans/076-ra-betfair-odds-collect.md for setup instructions."
            )

        try:
            cert_pem = base64.b64decode(cert_b64).decode("utf-8")
        except Exception as e:
            raise BetfairConfigError(f"Failed to decode BETFAIR_CERT_PEM_B64: {e}")

        try:
            key_pem = base64.b64decode(key_b64).decode("utf-8")
        except Exception as e:
            raise BetfairConfigError(f"Failed to decode BETFAIR_KEY_PEM_B64: {e}")

        return cls(
            app_key=app_key,
            username=username,
            password=password,
            cert_pem=cert_pem,
            key_pem=key_pem,
        )


@dataclass
class BetfairSession:
    """Active Betfair session with auth token."""

    session_token: str
    app_key: str
    cert_path: Path
    key_path: Path


def _setup_cert_files(config: BetfairConfig) -> Tuple[Path, Path]:
    """Write cert and key to temp files with secure permissions.

    Returns (cert_path, key_path).
    """
    betfair_dir = Path.home() / ".betfair"
    betfair_dir.mkdir(parents=True, exist_ok=True)

    cert_path = betfair_dir / "client-2048.crt"
    key_path = betfair_dir / "client-2048.key"

    # Write cert
    cert_path.write_text(config.cert_pem)
    cert_path.chmod(0o600)

    # Write key with restricted permissions
    key_path.write_text(config.key_pem)
    key_path.chmod(0o600)

    return cert_path, key_path


def _try_import_requests():
    """Import requests lazily."""
    try:
        import requests

        return requests
    except ImportError:
        return None


def authenticate(config: BetfairConfig) -> BetfairSession:
    """Authenticate with Betfair using certificate login.

    Raises BetfairAuthError on failure.
    """
    requests = _try_import_requests()
    if requests is None:
        raise BetfairAuthError("requests library not installed")

    # Setup cert files
    cert_path, key_path = _setup_cert_files(config)

    # Perform cert login
    headers = {
        "X-Application": config.app_key,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "username": config.username,
        "password": config.password,
    }

    try:
        response = requests.post(
            BETFAIR_CERT_LOGIN_URL,
            headers=headers,
            data=data,
            cert=(str(cert_path), str(key_path)),
            timeout=30,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise BetfairAuthError(f"Betfair login request failed: {e}")

    try:
        result = response.json()
    except json.JSONDecodeError as e:
        raise BetfairAuthError(f"Invalid JSON response from Betfair: {e}")

    if result.get("loginStatus") != "SUCCESS":
        status = result.get("loginStatus", "UNKNOWN")
        raise BetfairAuthError(f"Betfair login failed with status: {status}")

    session_token = result.get("sessionToken")
    if not session_token:
        raise BetfairAuthError("No session token in Betfair response")

    return BetfairSession(
        session_token=session_token,
        app_key=config.app_key,
        cert_path=cert_path,
        key_path=key_path,
    )


def _api_call(
    session: BetfairSession,
    endpoint: str,
    params: dict,
) -> dict:
    """Make authenticated Betfair API call."""
    requests = _try_import_requests()
    if requests is None:
        raise BetfairAuthError("requests library not installed")

    url = f"{BETFAIR_EXCHANGE_URL}/{endpoint}/"
    headers = {
        "X-Application": session.app_key,
        "X-Authentication": session.session_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        json=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def list_events(
    session: BetfairSession,
    date_local: str,
    *,
    country_code: str = "AU",
) -> List[dict]:
    """List horse racing events for a date.

    Returns list of event dicts with id, name, venue, etc.
    """
    # Parse date and build time range
    date_obj = datetime.strptime(date_local, "%Y-%m-%d")
    # Events from midnight to midnight Sydney time
    from_time = datetime(
        date_obj.year, date_obj.month, date_obj.day, 0, 0, 0, tzinfo=SYDNEY_TZ
    )
    to_time = datetime(
        date_obj.year, date_obj.month, date_obj.day, 23, 59, 59, tzinfo=SYDNEY_TZ
    )

    params = {
        "filter": {
            "eventTypeIds": [HORSE_RACING_EVENT_TYPE_ID],
            "marketCountries": [country_code],
            "marketStartTime": {
                "from": from_time.isoformat(),
                "to": to_time.isoformat(),
            },
        },
    }

    return _api_call(session, "listEvents", params)


def list_market_catalogue(
    session: BetfairSession,
    event_ids: List[str],
    *,
    max_results: int = 100,
) -> List[dict]:
    """List market catalogue for events.

    Returns markets with runner info.
    """
    params = {
        "filter": {
            "eventIds": event_ids,
            "marketTypeCodes": ["WIN"],  # Win markets only
        },
        "maxResults": str(max_results),
        "marketProjection": ["RUNNER_DESCRIPTION", "EVENT", "MARKET_START_TIME"],
    }

    return _api_call(session, "listMarketCatalogue", params)


def list_market_book(
    session: BetfairSession,
    market_ids: List[str],
) -> List[dict]:
    """Get current prices for markets."""
    params = {
        "marketIds": market_ids,
        "priceProjection": {
            "priceData": ["EX_BEST_OFFERS", "EX_TRADED"],
        },
    }

    return _api_call(session, "listMarketBook", params)


# ---------------------------------------------------------------------------
# Runner name matching
# ---------------------------------------------------------------------------


def _normalize_name(name: str) -> str:
    """Normalize runner name for matching.

    - Lowercase
    - Strip punctuation
    - Collapse whitespace
    """
    s = name.lower()
    s = re.sub(r"[^\w\s]", "", s)  # Remove punctuation
    s = re.sub(r"\s+", " ", s).strip()  # Collapse whitespace
    return s


def match_runners_fuzzy(
    betfair_runners: List[dict],
    ra_runner_names: List[str],
    *,
    min_score: int = 80,
) -> Tuple[Dict[str, dict], List[str]]:
    """Match Betfair runners to RA runner names using fuzzy matching.

    Returns:
        matched: Dict mapping RA name -> Betfair runner dict
        unmatched: List of RA names that couldn't be matched

    Uses rapidfuzz for matching (already a project dependency).
    Deterministic tie-breaking: picks lowest lexical candidate if equal scores.
    """
    from rapidfuzz import fuzz

    # Normalize all names
    ra_normalized = {_normalize_name(n): n for n in ra_runner_names}
    bf_normalized = {
        _normalize_name(r.get("runnerName", "")): r for r in betfair_runners
    }

    matched: Dict[str, dict] = {}
    unmatched: List[str] = []

    for ra_norm, ra_orig in sorted(ra_normalized.items()):
        best_score = 0
        best_candidates: List[Tuple[str, dict]] = []

        for bf_norm, bf_runner in bf_normalized.items():
            # Exact match first
            if ra_norm == bf_norm:
                best_score = 100
                best_candidates = [(bf_norm, bf_runner)]
                break

            # Fuzzy match
            score = fuzz.ratio(ra_norm, bf_norm)
            if score > best_score:
                best_score = score
                best_candidates = [(bf_norm, bf_runner)]
            elif score == best_score:
                best_candidates.append((bf_norm, bf_runner))

        if best_score >= min_score and best_candidates:
            # Deterministic tie-breaking: pick lowest lexical candidate
            best_candidates.sort(key=lambda x: x[0])
            _, bf_runner = best_candidates[0]
            matched[ra_orig] = bf_runner
        else:
            unmatched.append(ra_orig)

    return matched, unmatched


def extract_best_price(runner_book: dict) -> Optional[float]:
    """Extract best available back price from runner book.

    Prefers best back price, falls back to last traded price.
    Returns decimal odds (e.g., 3.5 for 5/2).
    """
    # Best available to back
    available_to_back = runner_book.get("ex", {}).get("availableToBack", [])
    if available_to_back:
        # First element is best price
        return available_to_back[0].get("price")

    # Fall back to last traded
    last_traded = runner_book.get("lastPriceTraded")
    if last_traded:
        return last_traded

    return None


# ---------------------------------------------------------------------------
# High-level odds fetch
# ---------------------------------------------------------------------------


@dataclass
class BetfairRaceOdds:
    """Odds for a single race from Betfair."""

    meeting_id: str
    race_number: int
    date_local: str
    market_id: str
    runners: List[Dict[str, Any]]
    unmatched_runners: List[str]
    captured_at: str


def fetch_race_odds(
    session: BetfairSession,
    meeting_id: str,
    race_number: int,
    date_local: str,
    ra_runner_names: List[str],
) -> Optional[BetfairRaceOdds]:
    """Fetch odds for a specific race from Betfair.

    Args:
        session: Authenticated Betfair session
        meeting_id: RA meeting ID (venue name)
        race_number: Race number (1-indexed)
        date_local: Date in YYYY-MM-DD format
        ra_runner_names: List of runner names from RA

    Returns:
        BetfairRaceOdds with matched runner prices, or None if not found
    """
    # List events for the date
    events = list_events(session, date_local)

    # Find matching event by venue name (fuzzy)
    venue_norm = _normalize_name(meeting_id)
    matching_event = None

    for event in events:
        event_obj = event.get("event", {})
        event_venue = event_obj.get("venue", "")
        if _normalize_name(event_venue) == venue_norm:
            matching_event = event_obj
            break

    if not matching_event:
        return None

    event_id = matching_event.get("id")
    if not event_id:
        return None

    # Get market catalogue for this event
    markets = list_market_catalogue(session, [event_id])

    # Find the market for this race number
    # Markets are named like "R1 1200m" or just by race time
    matching_market = None
    for market in markets:
        market_name = market.get("marketName", "")
        # Check if race number is in market name
        if f"R{race_number}" in market_name or f"Race {race_number}" in market_name:
            matching_market = market
            break

    # If no explicit match, try by ordering (markets should be ordered by time)
    if not matching_market and len(markets) >= race_number:
        # Sort by start time
        markets_sorted = sorted(
            markets, key=lambda m: m.get("marketStartTime", "")
        )
        if race_number <= len(markets_sorted):
            matching_market = markets_sorted[race_number - 1]

    if not matching_market:
        return None

    market_id = matching_market.get("marketId")
    betfair_runners = matching_market.get("runners", [])

    # Match runners
    matched, unmatched = match_runners_fuzzy(betfair_runners, ra_runner_names)

    # Get current prices
    books = list_market_book(session, [market_id])
    if not books:
        return None

    book = books[0]
    runner_books = {r.get("selectionId"): r for r in book.get("runners", [])}

    # Build runner odds
    runners = []
    for ra_name, bf_runner in matched.items():
        selection_id = bf_runner.get("selectionId")
        runner_book = runner_books.get(selection_id, {})
        price = extract_best_price(runner_book)

        runners.append(
            {
                "runner_name": ra_name,
                "betfair_name": bf_runner.get("runnerName"),
                "selection_id": selection_id,
                "price_now_dec": price,
            }
        )

    captured_at = datetime.now(SYDNEY_TZ).isoformat(timespec="seconds")

    return BetfairRaceOdds(
        meeting_id=meeting_id,
        race_number=race_number,
        date_local=date_local,
        market_id=market_id,
        runners=runners,
        unmatched_runners=unmatched,
        captured_at=captured_at,
    )
