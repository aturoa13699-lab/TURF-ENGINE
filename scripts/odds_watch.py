"""Live odds snapshot fetcher.

Watches odds pages and stores append-only snapshots over time.
This is for analysis/research only - does NOT feed into Lite ranking.

Requires optional dependencies:
    pip install httpx lxml
Or install with extras:
    pip install -e ".[scrape]"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Optional dependencies
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    from lxml import html as lxml_html
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False


def check_dependencies() -> None:
    """Check that required dependencies are available."""
    missing = []
    if not HTTPX_AVAILABLE:
        missing.append("httpx")
    if not LXML_AVAILABLE:
        missing.append("lxml")

    if missing:
        raise ImportError(
            f"Missing required dependencies: {', '.join(missing)}\n"
            f"Install with: pip install {' '.join(missing)}\n"
            f"Or: pip install -e '.[scrape]'"
        )


def fetch_url(url: str, timeout: float = 30.0) -> tuple[str, int]:
    """Fetch URL content.

    Returns:
        Tuple of (html_content, status_code)
    """
    check_dependencies()

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url)
        return response.text, response.status_code


def parse_odds_simple(html_content: str) -> List[Dict[str, Any]]:
    """Parse odds from HTML using simple table detection.

    This is a generic parser that looks for odds tables.
    Customize for specific sites as needed.
    """
    check_dependencies()

    doc = lxml_html.fromstring(html_content)
    odds_data = []

    # Look for common odds table patterns
    # This is a placeholder - customize selectors per source
    tables = doc.xpath("//table[contains(@class, 'odds') or contains(@class, 'runner')]")

    for table in tables:
        rows = table.xpath(".//tr")
        for row in rows:
            cells = row.xpath(".//td")
            if len(cells) >= 2:
                # Try to extract runner number and price
                runner_text = cells[0].text_content().strip()
                price_text = cells[-1].text_content().strip()

                try:
                    # Try to parse as number
                    runner_num = int(runner_text.split(".")[0].strip())
                    price = float(price_text.replace("$", "").strip())

                    odds_data.append({
                        "runner_number": runner_num,
                        "price": price,
                    })
                except (ValueError, IndexError):
                    continue

    return odds_data


def create_snapshot(
    url: str,
    meeting_id: str,
    race_number: int,
    odds_data: List[Dict[str, Any]],
    html_hash: str,
    status_code: int,
) -> Dict[str, Any]:
    """Create a snapshot record."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "meeting_id": meeting_id,
        "race_number": race_number,
        "url": url,
        "status_code": status_code,
        "html_hash": html_hash,
        "runner_count": len(odds_data),
        "odds": odds_data,
    }


def append_snapshot(snapshot: Dict[str, Any], output_file: Path) -> None:
    """Append snapshot to JSONL file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "a") as f:
        f.write(json.dumps(snapshot) + "\n")


def watch_odds(
    url: str,
    meeting_id: str,
    race_number: int,
    output_file: Path,
    interval_seconds: int = 60,
    duration_minutes: int = 30,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    """Watch odds page and capture snapshots.

    Args:
        url: URL to fetch
        meeting_id: Meeting identifier
        race_number: Race number
        output_file: JSONL file for append-only output
        interval_seconds: Seconds between fetches
        duration_minutes: Total duration to watch
        verbose: Print progress

    Returns:
        List of captured snapshots
    """
    check_dependencies()

    snapshots = []
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    iteration = 0

    if verbose:
        print(f"Starting odds watch for {meeting_id} R{race_number}")
        print(f"URL: {url}")
        print(f"Duration: {duration_minutes} minutes, interval: {interval_seconds}s")
        print(f"Output: {output_file}")
        print("-" * 50)

    while time.time() < end_time:
        iteration += 1
        try:
            html_content, status_code = fetch_url(url)
            html_hash = hashlib.md5(html_content.encode()).hexdigest()[:12]

            if status_code == 200:
                odds_data = parse_odds_simple(html_content)
            else:
                odds_data = []

            snapshot = create_snapshot(
                url=url,
                meeting_id=meeting_id,
                race_number=race_number,
                odds_data=odds_data,
                html_hash=html_hash,
                status_code=status_code,
            )

            append_snapshot(snapshot, output_file)
            snapshots.append(snapshot)

            if verbose:
                ts = snapshot["timestamp"][:19]
                print(f"[{iteration}] {ts} | status={status_code} | runners={len(odds_data)} | hash={html_hash}")

        except Exception as e:
            if verbose:
                print(f"[{iteration}] ERROR: {e}")

            # Record error snapshot
            error_snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "meeting_id": meeting_id,
                "race_number": race_number,
                "url": url,
                "error": str(e),
            }
            append_snapshot(error_snapshot, output_file)
            snapshots.append(error_snapshot)

        # Wait for next interval (unless we've exceeded duration)
        if time.time() + interval_seconds < end_time:
            time.sleep(interval_seconds)
        else:
            break

    if verbose:
        print("-" * 50)
        print(f"Completed: {len(snapshots)} snapshots captured")

    return snapshots


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Watch odds page and capture snapshots"
    )
    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="URL to fetch odds from",
    )
    parser.add_argument(
        "--meeting-id",
        type=str,
        required=True,
        help="Meeting identifier",
    )
    parser.add_argument(
        "--race",
        type=int,
        required=True,
        help="Race number",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("out/odds_snapshots.jsonl"),
        help="Output JSONL file (append-only)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between fetches (default: 60)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Total duration in minutes (default: 30)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    args = parser.parse_args()

    try:
        check_dependencies()
    except ImportError as e:
        print(f"ERROR: {e}")
        raise SystemExit(1)

    watch_odds(
        url=args.url,
        meeting_id=args.meeting_id,
        race_number=args.race,
        output_file=args.out,
        interval_seconds=args.interval,
        duration_minutes=args.duration,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
