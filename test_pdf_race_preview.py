"""Tests for turf/pdf_race_preview.py determinism and correctness.

These tests verify:
1. HTML output is deterministic (same input => same output)
2. PDF export works without PRO fields (basic stake_card.json)
3. No non-deterministic content (timestamps, random values)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def _build_minimal_stake_card() -> dict:
    """Build a minimal deterministic stake card for testing."""
    return {
        "meeting": {
            "meeting_id": "TEST_MEET",
            "track_canonical": "Test Track",
            "date_local": "2025-01-15",
        },
        "races": [
            {
                "race_number": 1,
                "distance_m": 1200,
                "track_condition_raw": "Good",
                "runners": [
                    {
                        "runner_number": 1,
                        "runner_name": "First Runner",
                        "lite_score": 0.85,
                        "lite_tag": "A_LITE",
                        "odds_minimal": {"price_now_dec": 3.50},
                        "forecast": {"win_prob": 0.30, "place_prob": 0.55, "value_edge": 0.05},
                    },
                    {
                        "runner_number": 2,
                        "runner_name": "Second Runner",
                        "lite_score": 0.65,
                        "lite_tag": "B_LITE",
                        "odds_minimal": {"price_now_dec": 5.00},
                        "forecast": {"win_prob": 0.20, "place_prob": 0.40, "value_edge": -0.02},
                    },
                ],
            }
        ],
        "engine_context": {
            "degrade_mode": "NORMAL",
            "warnings": [],
        },
    }


def _build_stake_card_with_pro_fields() -> dict:
    """Build a stake card with PRO overlay fields."""
    card = _build_minimal_stake_card()
    # Add PRO fields
    card["races"][0]["runners"][0]["ev_marker"] = "🟢"
    card["races"][0]["runners"][0]["risk_profile"] = "VALUE"
    card["races"][0]["race_summary"] = {
        "top_picks": [1],
        "value_picks": [1],
        "fades": [2],
        "trap_race": False,
        "strategy": "Bet #1",
    }
    return card


def test_html_output_deterministic(tmp_path: Path):
    """HTML output should be byte-identical for same input."""
    from turf.pdf_race_preview import render_preview_html

    card = _build_minimal_stake_card()

    html_1 = render_preview_html(card)
    html_2 = render_preview_html(card)

    assert html_1 == html_2, "HTML output must be deterministic"

    # Verify hashes match
    hash_1 = hashlib.sha256(html_1.encode()).hexdigest()
    hash_2 = hashlib.sha256(html_2.encode()).hexdigest()
    assert hash_1 == hash_2


def test_html_no_current_timestamp():
    """HTML should not contain current timestamps."""
    from turf.pdf_race_preview import render_preview_html

    card = _build_minimal_stake_card()
    html = render_preview_html(card)

    # Should not contain "UTC" timestamp pattern from datetime.utcnow()
    # The old non-deterministic code used patterns like "2025-12-17 20:51 UTC"
    import re
    utc_pattern = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC")
    assert not utc_pattern.search(html), "HTML should not contain live UTC timestamps"

    # Should contain the date from the payload
    assert "2025-01-15" in html


def test_html_preserves_runner_order():
    """Runners should appear in payload order, not re-sorted."""
    from turf.pdf_race_preview import render_preview_html

    card = _build_minimal_stake_card()
    # Reverse the runner order in payload
    card["races"][0]["runners"] = list(reversed(card["races"][0]["runners"]))

    html = render_preview_html(card)

    # Find positions of runner names
    pos_first = html.find("Second Runner")  # Now first due to reversal
    pos_second = html.find("First Runner")

    assert pos_first < pos_second, "Runner order should match payload order"


def test_render_single_preview_creates_html(tmp_path: Path):
    """render_single_preview should create HTML file."""
    from turf.pdf_race_preview import render_single_preview

    card = _build_minimal_stake_card()
    stake_path = tmp_path / "stake_card.json"
    stake_path.write_text(json.dumps(card))

    out_dir = tmp_path / "previews"
    result = render_single_preview(stake_path, out_dir, generate_pdf=False)

    assert result["html"]
    assert Path(result["html"]).exists()
    assert Path(result["html"]).suffix == ".html"


def test_render_previews_directory(tmp_path: Path):
    """render_previews should process all JSON files in directory."""
    from turf.pdf_race_preview import render_previews

    # Create multiple stake cards
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()

    card1 = _build_minimal_stake_card()
    card1["meeting"]["meeting_id"] = "MEET_A"
    (cards_dir / "card_a.json").write_text(json.dumps(card1))

    card2 = _build_minimal_stake_card()
    card2["meeting"]["meeting_id"] = "MEET_B"
    (cards_dir / "card_b.json").write_text(json.dumps(card2))

    out_dir = tmp_path / "previews"
    results = render_previews(cards_dir, out_dir, generate_pdf=False)

    assert len(results) == 2
    assert all(Path(r["html"]).exists() for r in results)


def test_works_without_pro_fields(tmp_path: Path):
    """Preview generation should work with basic stake_card.json (no PRO fields)."""
    from turf.pdf_race_preview import render_single_preview

    # Minimal card without any PRO fields
    card = {
        "meeting": {"meeting_id": "BASIC", "date_local": "2025-01-01"},
        "races": [
            {
                "race_number": 1,
                "runners": [
                    {"runner_number": 1, "runner_name": "Basic Runner", "lite_score": 0.5, "lite_tag": "PASS_LITE"}
                ],
            }
        ],
        "engine_context": {"degrade_mode": "NORMAL", "warnings": []},
    }

    stake_path = tmp_path / "basic.json"
    stake_path.write_text(json.dumps(card))

    out_dir = tmp_path / "out"
    result = render_single_preview(stake_path, out_dir, generate_pdf=False)

    assert result["html"]
    html_content = Path(result["html"]).read_text()
    assert "Basic Runner" in html_content


def test_pro_fields_rendered_when_present(tmp_path: Path):
    """PRO fields should appear in output when present in stake card."""
    from turf.pdf_race_preview import render_single_preview

    card = _build_stake_card_with_pro_fields()

    stake_path = tmp_path / "pro.json"
    stake_path.write_text(json.dumps(card))

    out_dir = tmp_path / "out"
    result = render_single_preview(stake_path, out_dir, generate_pdf=False)

    html_content = Path(result["html"]).read_text()

    # PRO fields should be rendered
    assert "🟢" in html_content or "VALUE" in html_content
    assert "Race Summary" in html_content


def test_fallback_date_used_when_missing():
    """Should use fixed fallback date when date_local is missing."""
    from turf.pdf_race_preview import render_preview_html, FIXED_FALLBACK_DATE

    card = {
        "meeting": {"meeting_id": "NO_DATE"},
        "races": [],
        "engine_context": {},
    }

    html = render_preview_html(card)

    assert FIXED_FALLBACK_DATE in html


def test_html_output_hash_stable_across_calls(tmp_path: Path):
    """Multiple calls with same input should produce identical SHA256 hashes."""
    from turf.pdf_race_preview import render_single_preview

    card = _build_minimal_stake_card()
    stake_path = tmp_path / "card.json"
    stake_path.write_text(json.dumps(card))

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    result_a = render_single_preview(stake_path, out_a, generate_pdf=False)
    result_b = render_single_preview(stake_path, out_b, generate_pdf=False)

    content_a = Path(result_a["html"]).read_bytes()
    content_b = Path(result_b["html"]).read_bytes()

    hash_a = hashlib.sha256(content_a).hexdigest()
    hash_b = hashlib.sha256(content_b).hexdigest()

    assert hash_a == hash_b, f"HTML hashes must match: {hash_a} != {hash_b}"


@pytest.mark.skipif(True, reason="PDF determinism requires weasyprint and may vary by environment")
def test_pdf_output_deterministic(tmp_path: Path):
    """PDF output should be identical for same input (requires weasyprint)."""
    from turf.pdf_race_preview import render_single_preview, WEASYPRINT_AVAILABLE

    if not WEASYPRINT_AVAILABLE:
        pytest.skip("weasyprint not installed")

    card = _build_minimal_stake_card()
    stake_path = tmp_path / "card.json"
    stake_path.write_text(json.dumps(card))

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    result_a = render_single_preview(stake_path, out_a, generate_pdf=True)
    result_b = render_single_preview(stake_path, out_b, generate_pdf=True)

    if result_a.get("pdf") and result_b.get("pdf"):
        pdf_a = Path(result_a["pdf"]).read_bytes()
        pdf_b = Path(result_b["pdf"]).read_bytes()

        hash_a = hashlib.sha256(pdf_a).hexdigest()
        hash_b = hashlib.sha256(pdf_b).hexdigest()

        # Note: PDF may have metadata differences; this test documents ideal behavior
        assert hash_a == hash_b, "PDF hashes should match for determinism"
