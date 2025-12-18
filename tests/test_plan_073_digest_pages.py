from __future__ import annotations

from pathlib import Path

from turf.digest_pages import render_digest_pages


def test_plan073_digest_pages_deterministic(tmp_path: Path) -> None:
    derived = tmp_path / "derived"
    public = tmp_path / "public" / "derived"
    (derived / "meetings").mkdir(parents=True, exist_ok=True)

    (derived / "daily_digest.md").write_text("# Daily\n- A\n")
    (derived / "daily_digest.json").write_text('{"ok":true}\n')
    (derived / "meetings" / "2025-12-18_DEMO.md").write_text("# Meeting\n- Bet\n")

    render_digest_pages(derived_dir=derived, public_derived_dir=public)
    daily1 = (public / "daily_digest.html").read_text()
    idx1 = (public / "index.html").read_text()
    m1 = (public / "meetings" / "2025-12-18_DEMO.html").read_text()

    # Re-run and ensure byte-identical output.
    render_digest_pages(derived_dir=derived, public_derived_dir=public)
    daily2 = (public / "daily_digest.html").read_text()
    idx2 = (public / "index.html").read_text()
    m2 = (public / "meetings" / "2025-12-18_DEMO.html").read_text()

    assert daily1 == daily2
    assert idx1 == idx2
    assert m1 == m2

    # Sanity: contains stable links
    assert "daily_digest.html" in idx1
    assert "meetings/2025-12-18_DEMO.html" in idx1

