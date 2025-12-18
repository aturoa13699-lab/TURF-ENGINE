"""Deterministic race preview renderer for HTML and PDF output.

This module generates formatted race preview documents from stake cards.
PDF rendering requires optional dependency: weasyprint (pip install turf[pdf])

Key invariants:
- Deterministic output: same input => same output bytes
- No current time usage - uses run_date from payload or fixed constant
- No randomness
- Stable ordering: races/runners in payload order (no re-sorting unless specified)
- Works with stake_card.json alone; PRO fields rendered only if present
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# PDF rendering is optional
try:
    from weasyprint import HTML as WeasyHTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False


# Fixed date used when no date is available in payload (deterministic)
FIXED_FALLBACK_DATE = "2000-01-01"

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

.race-summary {
    background: #f0f7ff;
    padding: 0.6em;
    margin: 0.5em 0;
    border-radius: 4px;
    font-size: 10pt;
}

.race-summary ul {
    margin: 0.3em 0;
    padding-left: 1.2em;
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


def _format_percentage(value: Optional[float]) -> str:
    """Format a probability as percentage."""
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _format_price(value: Optional[float]) -> str:
    """Format decimal odds."""
    if value is None:
        return "—"
    return f"${value:.2f}"


def _format_ev(value: Optional[float]) -> str:
    """Format expected value with color hint."""
    if value is None:
        return "—"
    pct = value * 100
    css_class = "positive" if pct > 0 else "negative"
    return f'<span class="{css_class}">{pct:+.1f}%</span>'


def _render_runner_row(runner: Dict[str, Any], is_top: bool = False) -> str:
    """Render a single runner row."""
    forecast = runner.get("forecast") or {}
    odds = runner.get("odds_minimal") or {}

    tag = runner.get("lite_tag", "")
    tag_class = tag.lower().replace("-", "_") if tag else "pass_lite"

    row_class = 'class="top-pick"' if is_top else ""

    # PRO fields if present
    ev_marker = ""
    risk_profile = ""
    if runner.get("ev_marker"):
        ev_marker = f' {runner.get("ev_marker")}'
    if runner.get("risk_profile"):
        risk_profile = f' [{runner.get("risk_profile")}]'

    return f"""
    <tr {row_class}>
        <td class="num">{runner.get('runner_number', '—')}</td>
        <td>{runner.get('runner_name', 'Unknown')}{ev_marker}{risk_profile}</td>
        <td><span class="tag tag-{tag_class}">{tag or '—'}</span></td>
        <td class="num">{runner.get('lite_score', 0):.3f}</td>
        <td class="num">{_format_price(odds.get('price_now_dec'))}</td>
        <td class="num">{_format_percentage(forecast.get('win_prob'))}</td>
        <td class="num">{_format_percentage(forecast.get('place_prob'))}</td>
        <td class="num">{_format_ev(forecast.get('value_edge'))}</td>
    </tr>
    """


def _render_race_summary(race_summary: Optional[Dict[str, Any]]) -> str:
    """Render race summary panel if present."""
    if not race_summary:
        return ""

    top_picks = race_summary.get("top_picks", [])
    value_picks = race_summary.get("value_picks", [])
    fades = race_summary.get("fades", [])
    trap_race = race_summary.get("trap_race", False)
    strategy = race_summary.get("strategy", "")

    return f"""
    <div class="race-summary">
        <strong>Race Summary:</strong>
        <ul>
            <li>Top picks: {', '.join(map(str, top_picks)) if top_picks else '—'}</li>
            <li>Value picks: {', '.join(map(str, value_picks)) if value_picks else '—'}</li>
            <li>Fades: {', '.join(map(str, fades)) if fades else '—'}</li>
            <li>Trap race: {'Yes' if trap_race else 'No'}</li>
            <li>Strategy: {strategy or '—'}</li>
        </ul>
    </div>
    """


def _render_race(race: Dict[str, Any], meeting: Dict[str, Any]) -> str:
    """Render a single race section.

    Preserves runner ordering from payload (deterministic).
    """
    runners = race.get("runners", [])

    # Preserve original order from payload - do NOT re-sort
    runner_rows = []
    for i, runner in enumerate(runners):
        runner_rows.append(_render_runner_row(runner, is_top=(i == 0)))

    race_summary = race.get("race_summary")
    summary_html = _render_race_summary(race_summary)

    return f"""
    <div class="race-header">
        <h2>Race {race.get('race_number', '?')} — {race.get('distance_m', '?')}m</h2>
        <div class="meta">
            Track condition: {race.get('track_condition_raw', 'Unknown')} |
            Field size: {len(runners)} runners
        </div>
    </div>
    {summary_html}
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
    """Render full preview HTML document.

    Args:
        stake_card: Loaded stake card payload (stake_card.json or stake_card_pro.json)

    Returns:
        Complete HTML document as string

    Determinism guarantees:
        - No current time usage; uses date_local from meeting or fixed fallback
        - Preserves race/runner ordering from input payload
        - No randomness
    """
    meeting = stake_card.get("meeting", {})
    races = stake_card.get("races", [])
    engine_context = stake_card.get("engine_context", {})

    meeting_id = meeting.get("meeting_id", "Unknown")
    track = meeting.get("track_canonical", meeting_id)
    # Use date from payload for determinism; fallback to fixed constant
    date = meeting.get("date_local", FIXED_FALLBACK_DATE)

    # Preserve race order from payload (deterministic)
    race_sections = []
    for race in races:
        race_sections.append(_render_race(race, meeting))

    warnings = engine_context.get("warnings", [])
    warnings_html = ""
    if warnings:
        warnings_html = f"""
        <div class="meta" style="color: #856404; background: #fff3cd; padding: 0.5em;">
            Warnings: {', '.join(warnings)}
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
        Generated by TURF ENGINE LITE | Run date: {date}
        <br>
        Forecasts are for informational purposes only. Lite ordering is deterministic.
    </div>
</body>
</html>"""


def render_preview_pdf(html_content: str, output_path: Path) -> bool:
    """Render HTML to PDF using WeasyPrint.

    Args:
        html_content: Complete HTML document string
        output_path: Where to write the PDF file

    Returns:
        True if successful, False if WeasyPrint not available

    Determinism note:
        WeasyPrint may include CreationDate metadata. For strict byte-reproducibility,
        consider post-processing to strip or normalize PDF metadata.
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
        List of generated file info dicts

    Determinism:
        - Only processes stake_card*.json files (ignores other JSON)
        - Deduplicates by (date, meeting_id) to avoid duplicate outputs
        - Processes files in sorted order for consistent results
        - Uses deterministic naming based on payload content
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Only process stake_card*.json files - ignore runner_vector.json etc.
    stake_files = sorted(stake_cards_dir.glob("stake_card*.json"))

    # Deduplicate by (date, meeting_id) - first file wins
    seen: set[tuple[str, str]] = set()
    generated = []

    for stake_file in stake_files:
        try:
            card = json.loads(stake_file.read_text())
        except (json.JSONDecodeError, IOError):
            continue

        # Skip files without valid stake card structure
        if "races" not in card:
            continue

        meeting = card.get("meeting", {})
        meeting_id = meeting.get("meeting_id", stake_file.stem)
        date = meeting.get("date_local", FIXED_FALLBACK_DATE)

        # Deduplicate by (date, meeting_id)
        key = (date, meeting_id)
        if key in seen:
            continue
        seen.add(key)

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


def render_single_preview(
    stake_card_path: Path,
    output_dir: Path,
    generate_pdf: bool = True,
) -> Dict[str, Any]:
    """Render preview for a single stake card file.

    Args:
        stake_card_path: Path to stake card JSON file
        output_dir: Directory for output files
        generate_pdf: Whether to generate PDF

    Returns:
        Dict with paths to generated files
    """
    card = json.loads(stake_card_path.read_text())
    meeting = card.get("meeting", {})
    meeting_id = meeting.get("meeting_id", stake_card_path.stem)
    date = meeting.get("date_local", FIXED_FALLBACK_DATE)

    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{date}_{meeting_id}"

    html_content = render_preview_html(card)
    html_path = output_dir / f"{base_name}.html"
    html_path.write_text(html_content)

    result = {
        "stake_card": str(stake_card_path),
        "meeting_id": meeting_id,
        "date": date,
        "html": str(html_path),
        "pdf": None,
    }

    if generate_pdf:
        pdf_path = output_dir / f"{base_name}.pdf"
        if render_preview_pdf(html_content, pdf_path):
            result["pdf"] = str(pdf_path)
        else:
            result["pdf_error"] = "weasyprint not installed"

    return result
