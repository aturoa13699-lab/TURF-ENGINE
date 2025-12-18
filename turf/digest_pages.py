from __future__ import annotations

"""Plan 073: Deterministic HTML wrappers for digest artifacts (derived-only).

This module converts digest Markdown artifacts into very simple HTML pages so
GitHub Pages can present them as clickable strategy sheets.

Determinism rules:
- No timestamps.
- Stable ordering based on sorted paths.
- Pure transformation of input files; does not mutate any stake card.
"""

import argparse
import html
from pathlib import Path
from typing import List, Tuple


def _wrap_pre_html(*, title: str, body_text: str) -> str:
    # Keep this intentionally minimal and deterministic.
    safe_title = html.escape(title, quote=True)
    safe_body = html.escape(body_text, quote=False)
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\" />\n"
        f"  <title>{safe_title}</title>\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
        "  <style>\n"
        "    body { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace; }\n"
        "    .wrap { max-width: 980px; margin: 24px auto; padding: 0 16px; }\n"
        "    pre { white-space: pre-wrap; word-break: break-word; }\n"
        "    a { text-decoration: none; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <div class=\"wrap\">\n"
        f"    <h1>{safe_title}</h1>\n"
        "    <p><a href=\"index.html\">← Back to digest index</a></p>\n"
        "    <pre>\n"
        f"{safe_body}\n"
        "    </pre>\n"
        "  </div>\n"
        "</body>\n"
        "</html>\n"
    )


def _discover_meeting_markdowns(derived_dir: Path) -> List[Path]:
    meetings_dir = derived_dir / "meetings"
    if not meetings_dir.exists() or not meetings_dir.is_dir():
        return []
    md_paths = [p for p in meetings_dir.rglob("*.md") if p.is_file()]
    return sorted(md_paths, key=lambda p: str(p))


def render_digest_pages(*, derived_dir: Path, public_derived_dir: Path) -> Tuple[Path | None, List[Path]]:
    """Render digest HTML pages deterministically.

    Returns: (daily_digest_html_path, per_meeting_html_paths)
    """
    public_derived_dir.mkdir(parents=True, exist_ok=True)
    (public_derived_dir / "meetings").mkdir(parents=True, exist_ok=True)

    daily_md = derived_dir / "daily_digest.md"
    daily_html_out: Path | None = None
    if daily_md.exists():
        body = daily_md.read_text()
        daily_html_out = public_derived_dir / "daily_digest.html"
        daily_html_out.write_text(_wrap_pre_html(title="TURF Daily Digest", body_text=body))

    meeting_html_paths: List[Path] = []
    for md_path in _discover_meeting_markdowns(derived_dir):
        body = md_path.read_text()
        rel = md_path.relative_to(derived_dir / "meetings")
        rel_html = rel.with_suffix(".html")
        title = rel.stem.replace("_", " ")
        out_path = public_derived_dir / "meetings" / rel_html
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_wrap_pre_html(title=f"Meeting Digest: {title}", body_text=body))
        meeting_html_paths.append(out_path)

    # Deterministic index page
    idx = public_derived_dir / "index.html"
    lines: List[str] = []
    lines.append("<!doctype html>")
    lines.append("<html lang=\"en\">")
    lines.append("<head>")
    lines.append("  <meta charset=\"utf-8\" />")
    lines.append("  <title>TURF Digest Index</title>")
    lines.append("  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />")
    lines.append("  <style>")
    lines.append("    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }")
    lines.append("    .wrap { max-width: 980px; margin: 24px auto; padding: 0 16px; }")
    lines.append("    code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace; }")
    lines.append("  </style>")
    lines.append("</head>")
    lines.append("<body>")
    lines.append("  <div class=\"wrap\">")
    lines.append("    <h1>TURF Digest Index</h1>")
    lines.append("    <p><a href=\"../index.html\">← Back to site home</a></p>")

    if daily_html_out is not None:
        lines.append("    <h2>Daily</h2>")
        lines.append("    <ul>")
        lines.append("      <li><a href=\"daily_digest.html\">Daily digest (HTML)</a></li>")
        lines.append("      <li><a href=\"daily_digest.md\">Daily digest (Markdown)</a></li>")
        lines.append("      <li><a href=\"daily_digest.json\">Daily digest (JSON)</a></li>")
        lines.append("    </ul>")

    if meeting_html_paths:
        lines.append("    <h2>Meetings</h2>")
        lines.append("    <ul>")
        for p in meeting_html_paths:
            rel = p.relative_to(public_derived_dir)
            lines.append(f"      <li><a href=\"{html.escape(str(rel), quote=True)}\">{html.escape(p.stem)}</a></li>")
        lines.append("    </ul>")

    lines.append("  </div>")
    lines.append("</body>")
    lines.append("</html>")
    idx.write_text("\n".join(lines) + "\n")

    return daily_html_out, meeting_html_paths


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render deterministic HTML pages for digest artifacts.")
    ap.add_argument("--derived-dir", required=True, help="Directory containing digest artifacts (daily_digest.md, meetings/*.md).")
    ap.add_argument("--public-derived-dir", required=True, help="Output directory under public/derived to write HTML pages.")
    args = ap.parse_args(argv)

    derived_dir = Path(args.derived_dir)
    public_derived_dir = Path(args.public_derived_dir)
    render_digest_pages(derived_dir=derived_dir, public_derived_dir=public_derived_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
