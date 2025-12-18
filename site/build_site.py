from __future__ import annotations

"""Static site renderer for Lite stake cards.

Reads stake card JSON files, computes simple staking suggestions, and renders
HTML suitable for GitHub Pages. Forecast fields are treated as overlay-only;
Lite ordering remains unchanged.
"""

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List

from turf.race_summary import summarize_race
from turf.value import derive_runner_value_fields

STYLE_PATH = Path(__file__).resolve().parent / "static" / "styles.css"
HEADER_TEMPLATE = Path(__file__).resolve().parent / "templates" / "header.html"
FOOTER_TEMPLATE = Path(__file__).resolve().parent / "templates" / "footer.html"


@dataclass
class RunnerView:
    runner_number: int
    runner_name: str
    lite_score: float
    lite_tag: str
    price_now_dec: float | None
    win_prob: float | None
    place_prob: float | None
    value_edge: float | None
    ev_1u: float | None
    certainty: float | None
    kelly_units: float
    ev_band: str | None
    ev_marker: str | None
    risk_profile: str | None


@dataclass
class RaceView:
    meeting_id: str
    meeting_label: str
    date_local: str
    race_number: int
    distance_m: int | None
    degrade_mode: str
    warnings: List[str]
    runners: List[RunnerView]
    artifact_name: str
    race_summary: dict | None

    @property
    def top_runner(self) -> RunnerView:
        return sorted(
            self.runners,
            key=lambda r: (
                -(r.win_prob if r.win_prob is not None else r.lite_score),
                -(r.lite_score),
                r.runner_number,
            ),
        )[0]


@dataclass
class SiteView:
    races: List[RaceView]


LITE_TAG_COLORS = {
    "A_LITE": "badge-a",
    "B_LITE": "badge-b",
    "PASS_LITE": "badge-pass",
}


def valid_price(price: float | None) -> bool:
    return isinstance(price, (int, float)) and math.isfinite(price) and price > 1.0


def kelly_units(win_prob: float | None, price: float | None, *, fraction: float = 0.25, cap: float = 3.0, min_ev: float = 0.02) -> float:
    if win_prob is None or not valid_price(price):
        return 0.0
    b = price - 1.0
    edge = win_prob * b - (1.0 - win_prob)
    if edge < min_ev:
        return 0.0
    stake_fraction = fraction * edge / b
    if stake_fraction <= 0:
        return 0.0
    return min(cap, round(stake_fraction * 10, 2))


def load_templates() -> tuple[str, str]:
    header = HEADER_TEMPLATE.read_text(encoding="utf-8")
    footer = FOOTER_TEMPLATE.read_text(encoding="utf-8")
    return header, footer


def apply_header(template: str, *, title: str, prefix: str) -> str:
    return template.replace("{{TITLE}}", title).replace("{{PREFIX}}", prefix)


def render_badge(tag: str) -> str:
    css = LITE_TAG_COLORS.get(tag, "badge-pass")
    return f"<span class=\"badge {css}\">{tag}</span>"


def render_runner_row(runner: RunnerView) -> str:
    price_text = f"{runner.price_now_dec:.2f}" if runner.price_now_dec is not None else "—"
    win_text = f"{runner.win_prob:.2%}" if runner.win_prob is not None else "—"
    place_text = f"{runner.place_prob:.2%}" if runner.place_prob is not None else "—"
    edge_text = f"{runner.value_edge:+.2%}" if runner.value_edge is not None else "—"
    ev_text = f"{runner.ev_1u:+.2f}" if runner.ev_1u is not None else "—"
    units = f"{runner.kelly_units:.2f}" if runner.kelly_units else "—"
    ev_marker = runner.ev_marker or ""
    band = runner.ev_band or ""
    risk = runner.risk_profile or ""
    return """
    <tr>
      <td class="num">{runner_number}</td>
      <td>{name}</td>
      <td>{badge}</td>
      <td class="num">{lite_score:.3f}</td>
      <td class="num">{price}</td>
      <td class="num">{win}</td>
      <td class="num">{place}</td>
      <td class="num">{edge}</td>
      <td class="num">{ev}</td>
      <td class="num">{ev_marker}</td>
      <td class="num">{band}</td>
      <td class="num">{risk}</td>
      <td class="num">{units}</td>
    </tr>
    """.format(
        runner_number=runner.runner_number,
        name=runner.runner_name,
        badge=render_badge(runner.lite_tag),
        lite_score=runner.lite_score,
        price=price_text,
        win=win_text,
        place=place_text,
        edge=edge_text,
        ev=ev_text,
        ev_marker=ev_marker,
        band=band,
        risk=risk,
        units=units,
    )


def render_race_page(race: RaceView, header: str, footer: str) -> str:
    body_rows = "\n".join(render_runner_row(r) for r in race.runners)
    warnings = ", ".join(race.warnings) if race.warnings else "None"
    title = f"{race.meeting_label} R{race.race_number}"
    page_header = apply_header(header, title=title, prefix="../")
    summary = race.race_summary
    if summary:
        summary_block = """
    <section class="race-summary">
      <h2>Race summary</h2>
      <ul>
        <li><strong>Top picks:</strong> {top_picks}</li>
        <li><strong>Value picks:</strong> {value_picks}</li>
        <li><strong>Fades:</strong> {fades}</li>
        <li><strong>Trap race:</strong> {trap_race}</li>
        <li><strong>Strategy:</strong> {strategy}</li>
      </ul>
    </section>
    """.format(
            top_picks=summary.get("top_picks", []),
            value_picks=summary.get("value_picks", []),
            fades=summary.get("fades", []),
            trap_race=summary.get("trap_race", False),
            strategy=summary.get("strategy", ""),
        )
    else:
        summary_block = ""
    return page_header + f"""
  <main>
    <h1>{race.meeting_label} — Race {race.race_number}</h1>
    <p class="meta">Date: {race.date_local} · Distance: {race.distance_m or '—'}m · Degrade mode: {race.degrade_mode} · Warnings: {warnings}</p>
    <p class="meta">Source artifact: {race.artifact_name}</p>
    {summary_block}
    <table class="runners">
      <thead>
        <tr><th>#</th><th>Runner</th><th>Tag</th><th>LiteScore</th><th>Price</th><th>Win%</th><th>Place%</th><th>Value</th><th>EV (1u)</th><th>EV</th><th>Band</th><th>Risk</th><th>Units</th></tr>
      </thead>
      <tbody>
        {body_rows}
      </tbody>
    </table>
  </main>
""" + footer


def render_index(site: SiteView, header: str, footer: str) -> str:
    rows = []
    for race in sorted(site.races, key=lambda r: (r.date_local, r.meeting_id, r.race_number)):
        runner = race.top_runner
        win_text = f"{runner.win_prob:.2%}" if runner.win_prob is not None else "—"
        link = f"races/{race.meeting_id}_R{race.race_number}.html"
        rows.append(
            """
        <tr>
          <td>{date}</td>
          <td>{meeting}</td>
          <td class="num">{race_number}</td>
          <td>{runner_name}</td>
          <td>{badge}</td>
          <td class="num">{lite_score:.3f}</td>
          <td class="num">{win}</td>
          <td class="num"><a href="{link}">View</a></td>
        </tr>
        """.format(
                date=race.date_local,
                meeting=race.meeting_label,
                race_number=race.race_number,
                runner_name=runner.runner_name,
                badge=render_badge(runner.lite_tag),
                lite_score=runner.lite_score,
                win=win_text,
                link=link,
            )
        )
    rows_html = "\n".join(rows)
    page_header = apply_header(header, title="Stake cards", prefix="")
    return page_header + f"""
  <main>
    <h1>TURF ENGINE LITE — Daily stake cards</h1>
    <p class="meta">Overlay fields are display-only; ordering remains LiteScore + tie-gate.</p>
    <table class="runners">
      <thead><tr><th>Date</th><th>Meeting</th><th>Race</th><th>Top pick</th><th>Tag</th><th>LiteScore</th><th>Win%</th><th></th></tr></thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </main>
""" + footer


VALUE_FIELDS = [
    "ev",
    "ev_band",
    "ev_marker",
    "confidence_class",
    "risk_profile",
    "model_vs_market_alert",
]


def parse_runner(runner: dict, *, derive_on_render: bool = False) -> RunnerView:
    odds_block = runner.get("odds_minimal") or {}
    price = odds_block.get("price_now_dec")
    forecast = runner.get("forecast") or {}
    win_prob = forecast.get("win_prob")
    derived = derive_runner_value_fields(runner)
    return RunnerView(
        runner_number=runner["runner_number"],
        runner_name=runner.get("runner_name", ""),
        lite_score=runner.get("lite_score", 0.0),
        lite_tag=runner.get("lite_tag", "PASS_LITE"),
        price_now_dec=price,
        win_prob=win_prob,
        place_prob=forecast.get("place_prob"),
        value_edge=forecast.get("value_edge"),
        ev_1u=forecast.get("ev_1u"),
        certainty=forecast.get("certainty"),
        kelly_units=kelly_units(win_prob, price),
        ev_band=derived.get("ev_band"),
        ev_marker=derived.get("ev_marker"),
        risk_profile=derived.get("risk_profile"),
    )


def parse_stake_card(path: Path, *, derive_on_render: bool) -> List[RaceView]:
    payload = json.loads(path.read_text())
    meeting = payload.get("meeting", {})
    meeting_id = meeting.get("meeting_id", "UNKNOWN_MEETING")
    meeting_label = f"{meeting.get('track_canonical', meeting_id)} ({meeting_id})"
    date_local = meeting.get("date_local", "")
    races = []
    for race in payload.get("races", []):
        runners = [parse_runner(r, derive_on_render=derive_on_render) for r in race.get("runners", [])]
        if derive_on_render:
            race_summary = race.get("race_summary") or summarize_race(race)
        else:
            race_summary = race.get("race_summary")
        races.append(
            RaceView(
                meeting_id=meeting_id,
                meeting_label=meeting_label,
                date_local=date_local,
                race_number=race.get("race_number"),
                distance_m=race.get("distance_m"),
                degrade_mode=payload.get("engine_context", {}).get("degrade_mode", "UNKNOWN"),
                warnings=payload.get("engine_context", {}).get("warnings", []),
                runners=runners,
                artifact_name=path.name,
                race_summary=race_summary,
            )
        )
    return races


def copy_static(out_dir: Path) -> None:
    static_dir = out_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    static_css = STYLE_PATH.read_text(encoding="utf-8")
    (static_dir / "styles.css").write_text(static_css, encoding="utf-8")


def build_site(stake_dir: Path, out_dir: Path, *, derive_on_render: bool = False) -> None:
    stake_files = sorted(stake_dir.glob("*.json"))
    if not stake_files:
        raise SystemExit(f"No stake cards found in {stake_dir}")

    races: List[RaceView] = []
    for path in stake_files:
        races.extend(parse_stake_card(path, derive_on_render=derive_on_render))

    site = SiteView(races=races)
    header, footer = load_templates()

    out_dir.mkdir(parents=True, exist_ok=True)
    races_dir = out_dir / "races"
    races_dir.mkdir(exist_ok=True)

    for race in site.races:
        page_html = render_race_page(race, header, footer)
        race_path = races_dir / f"{race.meeting_id}_R{race.race_number}.html"
        race_path.write_text(page_html, encoding="utf-8")

    index_html = render_index(site, header, footer)
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    copy_static(out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render static pages from Lite stake cards")
    parser.add_argument("--stake-cards", type=Path, default=Path("out/stake_cards"), help="Directory containing stake card JSON files")
    parser.add_argument("--out", type=Path, default=Path("public"), help="Output directory for the static site")
    parser.add_argument(
        "--derive-on-render",
        action="store_true",
        help="Optionally derive EV/race summaries during rendering (default: off)",
    )
    args = parser.parse_args()

    build_site(args.stake_cards, args.out, derive_on_render=args.derive_on_render)


if __name__ == "__main__":
    main()
