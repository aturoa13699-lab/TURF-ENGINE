from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import List, Tuple


def load_stake_cards(directory: Path) -> List[Tuple[str, dict]]:
    cards: List[Tuple[str, dict]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            cards.append((path.name, data))
        except Exception:
            continue
    return cards


def format_runner_row(runner: dict) -> str:
    score = runner.get("lite_score")
    tag = runner.get("lite_tag") or ""
    return """<tr><td>{num}</td><td>{name}</td><td>{score:.3f}</td><td><span class='tag tag-{tag_lower}'>{tag}</span></td></tr>""".format(
        num=html.escape(str(runner.get("runner_number", "?"))),
        name=html.escape(runner.get("runner_name", "")),
        score=float(score) if isinstance(score, (int, float)) else 0.0,
        tag=html.escape(tag),
        tag_lower=html.escape(tag.lower() if isinstance(tag, str) else "unknown"),
    )


def render_table(card: dict, source_name: str) -> str:
    meeting = card.get("meeting", {})
    races = card.get("races", []) or []
    blocks: List[str] = []
    for race in races:
        rows = race.get("runners", []) or []
        runner_rows = "\n".join(format_runner_row(r) for r in rows)
        blocks.append(
            f"""
            <section class="race">
              <h3>{html.escape(meeting.get('track_canonical', meeting.get('meeting_id', 'Unknown Track')))} — Race {html.escape(str(race.get('race_number', '?')))}</h3>
              <p>Distance: {html.escape(str(race.get('distance_m', 'N/A')))}m · Source: {html.escape(source_name)}</p>
              <table>
                <thead><tr><th>#</th><th>Runner</th><th>LiteScore</th><th>Tag</th></tr></thead>
                <tbody>
                  {runner_rows}
                </tbody>
              </table>
            </section>
            """
        )
    return "\n".join(blocks)


def build_html(date_label: str, cards: List[Tuple[str, dict]]) -> str:
    tables = "\n".join(render_table(card, name) for name, card in cards)
    empty = "<p>No stake cards were generated.</p>" if not cards else ""
    return f"""
<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <style>
    body {{ font-family: Arial, sans-serif; color: #111; }}
    .race {{ margin-bottom: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; }}
    th {{ background: #f7f7f7; text-align: left; }}
    .tag {{ padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
    .tag-a_lite {{ background: #d1e7dd; color: #0f5132; }}
    .tag-b_lite {{ background: #cff4fc; color: #055160; }}
    .tag-pass_lite {{ background: #fef3c7; color: #92400e; }}
  </style>
</head>
<body>
  <h2>TURF ENGINE LITE — Daily Stake Cards ({html.escape(date_label)})</h2>
  {empty}
  {tables}
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render stake cards into an HTML summary")
    parser.add_argument("--stake-cards", type=Path, default=Path("out/stake_cards"), help="Directory containing stake card JSON files")
    parser.add_argument("--date", type=str, required=True, help="Date label to display")
    parser.add_argument("--out", type=Path, default=Path("out/email/rendered_summary.html"), help="Where to write the HTML output")
    args = parser.parse_args()

    cards = load_stake_cards(args.stake_cards)
    html_doc = build_html(args.date, cards)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html_doc)
    print(f"Rendered {len(cards)} stake cards to {args.out}")


if __name__ == "__main__":
    main()
