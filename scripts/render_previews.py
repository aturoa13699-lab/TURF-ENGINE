"""Render race previews as HTML and optionally PDF.

This module generates formatted race preview documents from stake cards,
suitable for email attachments or printing.

PDF rendering requires optional dependency: weasyprint
Install with: pip install weasyprint
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# PDF rendering is optional
try:
    from weasyprint import HTML as WeasyHTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False


CSS_STYLES = """
@page {
    size: A4;
    margin: 1.5cm;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.4;
    color: #1a1a1a;
    max-width: 800px;
    margin: 0 auto;
}

h1 {
    color: #0066cc;
    font-size: 18pt;
    margin-bottom: 0.5em;
    border-bottom: 2px solid #0066cc;
    padding-bottom: 0.3em;
}

h2 {
    color: #333;
    font-size: 14pt;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
}

.meta {
    color: #666;
    font-size: 10pt;
    margin-bottom: 1em;
}

.race-header {
    background: #f5f5f5;
    padding: 0.8em;
    margin: 1em 0 0.5em 0;
    border-left: 4px solid #0066cc;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.5em 0 1.5em 0;
    font-size: 10pt;
}

th, td {
    border: 1px solid #ddd;
    padding: 6px 8px;
    text-align: left;
}

th {
    background: #f0f0f0;
    font-weight: 600;
}

.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
}

.tag {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 9pt;
    font-weight: 600;
}

.tag-a_lite { background: #d4edda; color: #155724; }
.tag-b_lite { background: #cce5ff; color: #004085; }
.tag-pass_lite { background: #fff3cd; color: #856404; }

.positive { color: #28a745; }
.negative { color: #dc3545; }

.top-pick {
    background: #fffde7;
}

.footer {
    margin-top: 2em;
    padding-top: 1em;
    border-top: 1px solid #ddd;
    font-size: 9pt;
    color: #888;
    text-align: center;
}
"""


def format_percentage(value: Optional[float]) -> str:
    """Format a probability as percentage."""
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def format_price(value: Optional[float]) -> str:
    """Format decimal odds."""
    if value is None:
        return "—"
    return f"${value:.2f}"


def format_ev(value: Optional[float]) -> str:
    """Format expected value with color hint."""
    if value is None:
        return "—"
    pct = value * 100
    css_class = "positive" if pct > 0 else "negative"
    return f'<span class="{css_class}">{pct:+.1f}%</span>'


def render_runner_row(runner: Dict[str, Any], is_top: bool = False) -> str:
    """Render a single runner row."""
    forecast = runner.get("forecast") or {}
    odds = runner.get("odds_minimal") or {}

    tag = runner.get("lite_tag", "")
    tag_class = tag.lower().replace("-", "_") if tag else "pass_lite"

    row_class = 'class="top-pick"' if is_top else ""

    return f"""
    <tr {row_class}>
        <td class="num">{runner.get('runner_number', '—')}</td>
        <td>{runner.get('runner_name', 'Unknown')}</td>
        <td><span class="tag tag-{tag_class}">{tag or '—'}</span></td>
        <td class="num">{runner.get('lite_score', 0):.3f}</td>
        <td class="num">{format_price(odds.get('price_now_dec'))}</td>
        <td class="num">{format_percentage(forecast.get('win_prob'))}</td>
        <td class="num">{format_percentage(forecast.get('place_prob'))}</td>
        <td class="num">{format_ev(forecast.get('value_edge'))}</td>
    </tr>
    """


def render_race(race: Dict[str, Any], meeting: Dict[str, Any]) -> str:
    """Render a single race section."""
    runners = race.get("runners", [])

    # Sort by lite_score descending
    sorted_runners = sorted(runners, key=lambda r: -(r.get("lite_score") or 0))

    runner_rows = []
    for i, runner in enumerate(sorted_runners):
        runner_rows.append(render_runner_row(runner, is_top=(i == 0)))

    return f"""
    <div class="race-header">
        <h2>Race {race.get('race_number', '?')} — {race.get('distance_m', '?')}m</h2>
        <div class="meta">
            Track condition: {race.get('track_condition_raw', 'Unknown')} |
            Field size: {len(runners)} runners
        </div>
    </div>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Runner</th>
                <th>Tag</th>
                <th>LiteScore</th>
                <th>Price</th>
                <th>Win%</th>
                <th>Place%</th>
                <th>Edge</th>
            </tr>
        </thead>
        <tbody>
            {''.join(runner_rows)}
        </tbody>
    </table>
    """


def render_preview_html(stake_card: Dict[str, Any]) -> str:
    """Render full preview HTML document."""
    meeting = stake_card.get("meeting", {})
    races = stake_card.get("races", [])
    engine_context = stake_card.get("engine_context", {})

    meeting_id = meeting.get("meeting_id", "Unknown")
    track = meeting.get("track_canonical", meeting_id)
    date = meeting.get("date_local", "Unknown")

    race_sections = []
    for race in sorted(races, key=lambda r: r.get("race_number", 0)):
        race_sections.append(render_race(race, meeting))

    warnings = engine_context.get("warnings", [])
    warnings_html = ""
    if warnings:
        warnings_html = f"""
        <div class="meta" style="color: #856404; background: #fff3cd; padding: 0.5em;">
            ⚠️ Warnings: {', '.join(warnings)}
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TURF Preview — {track} ({date})</title>
    <style>{CSS_STYLES}</style>
</head>
<body>
    <h1>TURF ENGINE LITE — Race Preview</h1>
    <div class="meta">
        <strong>{track}</strong> | {date} |
        Mode: {engine_context.get('degrade_mode', 'NORMAL')}
    </div>
    {warnings_html}

    {''.join(race_sections)}

    <div class="footer">
        Generated by TURF ENGINE LITE | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
        <br>
        Forecasts are for informational purposes only. Lite ordering is deterministic and unchanged by overlays.
    </div>
</body>
</html>"""


def render_preview_pdf(html_content: str, output_path: Path) -> bool:
    """Render HTML to PDF using WeasyPrint.

    Returns True if successful, False if WeasyPrint not available.
    """
    if not WEASYPRINT_AVAILABLE:
        return False

    doc = WeasyHTML(string=html_content)
    doc.write_pdf(output_path)
    return True


def render_previews(
    stake_cards_dir: Path,
    output_dir: Path,
    generate_pdf: bool = True,
) -> List[Dict[str, Any]]:
    """Render previews for all stake cards in a directory.

    Args:
        stake_cards_dir: Directory containing stake card JSON files
        output_dir: Directory for output files
        generate_pdf: Whether to generate PDF (requires weasyprint)

    Returns:
        List of generated file info
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    stake_files = sorted(stake_cards_dir.glob("*.json"))

    for stake_file in stake_files:
        try:
            card = json.loads(stake_file.read_text())
        except (json.JSONDecodeError, IOError):
            continue

        meeting = card.get("meeting", {})
        meeting_id = meeting.get("meeting_id", stake_file.stem)
        date = meeting.get("date_local", "unknown")

        base_name = f"{date}_{meeting_id}"

        # Render HTML
        html_content = render_preview_html(card)
        html_path = output_dir / f"{base_name}.html"
        html_path.write_text(html_content)

        result = {
            "stake_card": str(stake_file),
            "meeting_id": meeting_id,
            "date": date,
            "html": str(html_path),
            "pdf": None,
        }

        # Render PDF if requested
        if generate_pdf:
            pdf_path = output_dir / f"{base_name}.pdf"
            if render_preview_pdf(html_content, pdf_path):
                result["pdf"] = str(pdf_path)
            else:
                result["pdf_error"] = "weasyprint not installed"

        generated.append(result)

    return generated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render race previews as HTML/PDF from stake cards"
    )
    parser.add_argument(
        "--stake-cards",
        type=Path,
        required=True,
        help="Directory containing stake card JSON files",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("out/previews"),
        help="Output directory for HTML/PDF files",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip PDF generation (HTML only)",
    )
    parser.add_argument(
        "--single",
        type=Path,
        help="Render a single stake card file instead of directory",
    )
    args = parser.parse_args()

    if args.single:
        # Single file mode
        if not args.single.exists():
            raise SystemExit(f"File not found: {args.single}")

        card = json.loads(args.single.read_text())
        html_content = render_preview_html(card)

        args.out.mkdir(parents=True, exist_ok=True)
        html_path = args.out / f"{args.single.stem}.html"
        html_path.write_text(html_content)
        print(f"HTML: {html_path}")

        if not args.no_pdf:
            pdf_path = args.out / f"{args.single.stem}.pdf"
            if render_preview_pdf(html_content, pdf_path):
                print(f"PDF: {pdf_path}")
            else:
                print("PDF skipped: weasyprint not installed")

    else:
        # Directory mode
        if not args.stake_cards.is_dir():
            raise SystemExit(f"Not a directory: {args.stake_cards}")

        results = render_previews(
            args.stake_cards,
            args.out,
            generate_pdf=not args.no_pdf,
        )

        print(f"Rendered {len(results)} preview(s) to {args.out}")
        for r in results:
            print(f"  - {r['meeting_id']}: HTML={r['html']}, PDF={r.get('pdf', 'skipped')}")


if __name__ == "__main__":
    main()
