from __future__ import annotations

"""Plan 076: Tests for RA + market odds ingestion and stake card collection.

Tests verify:
1. Stake cards are generated deterministically (same output across two runs)
2. Meeting/race ordering is stable (sorted by meeting_id, race_number)
3. Runner mapping preserves runner_number stability
4. Digest artifacts are generated and stable
5. No mutation of input fixture files (compare bytes before/after)
"""

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from turf.collect_pipeline import (
    PipelineConfig,
    process_meeting,
    process_race,
    run_pipeline,
)
from turf.odds_collect import FixtureAdapter, get_odds_adapter
from turf.ra_collect import (
    RaceCapture,
    capture_meeting,
    discover_captured_meetings,
    load_captured_meeting,
    parse_captured_race,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RA_FIXTURES = FIXTURES_DIR / "ra"
ODDS_FIXTURES = FIXTURES_DIR / "odds"
TEST_DATE = "2025-12-18"
TEST_MEETING = "TEST_RANDWICK"


def _hash_file(path: Path) -> str:
    """Compute SHA256 hash of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_dir(dir_path: Path) -> dict:
    """Hash all files in a directory for comparison."""
    hashes = {}
    for f in sorted(dir_path.rglob("*")):
        if f.is_file():
            hashes[str(f.relative_to(dir_path))] = _hash_file(f)
    return hashes


# ---------------------------------------------------------------------------
# RA Collect tests
# ---------------------------------------------------------------------------


class TestRaCollect:
    def test_discover_captured_meetings(self) -> None:
        """Test meeting discovery from fixtures."""
        meetings = discover_captured_meetings(RA_FIXTURES, TEST_DATE)
        assert "TEST_RANDWICK" in meetings
        assert "TEST_ROSEHILL" in meetings
        # Meetings should be sorted
        assert meetings == sorted(meetings)

    def test_load_captured_meeting(self) -> None:
        """Test loading a captured meeting."""
        capture = load_captured_meeting(RA_FIXTURES, TEST_DATE, TEST_MEETING)
        assert capture is not None
        assert capture.meeting_id == TEST_MEETING
        assert capture.date_local == TEST_DATE
        assert len(capture.races) == 2  # race_1.html and race_2.html

    def test_race_capture_ordering(self) -> None:
        """Test that races are loaded in deterministic order by race number."""
        capture = load_captured_meeting(RA_FIXTURES, TEST_DATE, TEST_MEETING)
        assert capture is not None
        race_numbers = [r.race_number for r in capture.races]
        assert race_numbers == sorted(race_numbers)
        assert race_numbers == [1, 2]

    def test_parse_captured_race(self) -> None:
        """Test parsing a captured race HTML."""
        capture = load_captured_meeting(RA_FIXTURES, TEST_DATE, TEST_MEETING)
        assert capture is not None

        race1 = capture.races[0]
        parsed = parse_captured_race(race1)

        assert parsed.meeting_id == TEST_MEETING
        assert parsed.race_number == 1
        assert len(parsed.runners) == 4
        assert parsed.runners[0].runner_name == "Fixture Horse A"
        assert parsed.runners[0].runner_number == 1

    def test_runner_number_stability(self) -> None:
        """Test that runner numbers are preserved through parsing."""
        capture = load_captured_meeting(RA_FIXTURES, TEST_DATE, TEST_MEETING)
        assert capture is not None

        for race in capture.races:
            parsed = parse_captured_race(race)
            # Runners should be sorted by runner_number
            runner_numbers = [r.runner_number for r in parsed.runners]
            assert runner_numbers == sorted(runner_numbers)

    def test_no_mutation_of_fixture_files(self) -> None:
        """Test that loading and parsing does not mutate fixture files."""
        # Hash fixtures before
        hashes_before = _hash_dir(RA_FIXTURES / TEST_DATE)

        # Load and parse
        capture = load_captured_meeting(RA_FIXTURES, TEST_DATE, TEST_MEETING)
        assert capture is not None
        for race in capture.races:
            parse_captured_race(race)

        # Hash fixtures after
        hashes_after = _hash_dir(RA_FIXTURES / TEST_DATE)

        assert hashes_before == hashes_after


# ---------------------------------------------------------------------------
# Odds Collect tests
# ---------------------------------------------------------------------------


class TestOddsCollect:
    def test_fixture_adapter_loads_odds(self) -> None:
        """Test that fixture adapter loads odds from fixture files."""
        adapter = FixtureAdapter(ODDS_FIXTURES)
        snapshot = adapter.fetch_odds(TEST_MEETING, 1, TEST_DATE)

        assert snapshot is not None
        assert snapshot.meeting_id == TEST_MEETING
        assert snapshot.race_number == 1
        assert len(snapshot.runners) == 4
        assert snapshot.runners[0]["runner_name"] == "Fixture Horse A"

    def test_none_adapter_returns_none(self) -> None:
        """Test that none adapter returns no odds."""
        adapter = get_odds_adapter("none")
        snapshot = adapter.fetch_odds(TEST_MEETING, 1, TEST_DATE)
        assert snapshot is None

    def test_adapter_factory(self) -> None:
        """Test odds adapter factory."""
        none_adapter = get_odds_adapter("none")
        assert none_adapter.source_name == "none"

        fixture_adapter = get_odds_adapter("fixture", fixtures_dir=ODDS_FIXTURES)
        assert fixture_adapter.source_name == "fixture"


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------


class TestCollectPipeline:
    def test_process_race_produces_stake_card(self, tmp_path: Path) -> None:
        """Test that process_race produces a valid stake card."""
        capture = load_captured_meeting(RA_FIXTURES, TEST_DATE, TEST_MEETING)
        assert capture is not None

        adapter = get_odds_adapter("none")
        artifacts = process_race(
            capture.races[0], adapter, default_distance_m=1200, apply_pro=False
        )

        assert artifacts.meeting_id == TEST_MEETING
        assert artifacts.race_number == 1
        assert "engine_context" in artifacts.stake_card
        assert "races" in artifacts.stake_card
        assert len(artifacts.stake_card["races"]) == 1
        assert len(artifacts.stake_card["races"][0]["runners"]) == 4

    def test_process_race_with_odds_fixture(self) -> None:
        """Test that odds are merged when using fixture adapter."""
        capture = load_captured_meeting(RA_FIXTURES, TEST_DATE, TEST_MEETING)
        assert capture is not None

        adapter = FixtureAdapter(ODDS_FIXTURES)
        artifacts = process_race(capture.races[0], adapter, apply_pro=False)

        # The odds should have been merged
        # Fixture odds had different prices than RA
        runners = artifacts.stake_card["races"][0]["runners"]
        # Find runner by name and check price was updated
        runner_a = next(r for r in runners if r["runner_name"] == "Fixture Horse A")
        # Odds fixture has 3.60, RA had 3.50
        assert runner_a["odds_minimal"]["price_now_dec"] == 3.60

    def test_process_meeting_all_races(self) -> None:
        """Test that process_meeting handles all races."""
        capture = load_captured_meeting(RA_FIXTURES, TEST_DATE, TEST_MEETING)
        assert capture is not None

        adapter = get_odds_adapter("none")
        meeting_artifacts = process_meeting(capture, adapter, apply_pro=False)

        assert meeting_artifacts.meeting_id == TEST_MEETING
        assert len(meeting_artifacts.races) == 2

    def test_pipeline_determinism(self, tmp_path: Path) -> None:
        """Test that the pipeline produces identical output on repeated runs."""
        # Copy fixtures to tmp_path to use as capture_dir
        capture_dir = tmp_path / "raw"
        shutil.copytree(RA_FIXTURES, capture_dir / "ra")

        out1 = tmp_path / "out1"
        out2 = tmp_path / "out2"

        config1 = PipelineConfig(
            date_local=TEST_DATE,
            capture_dir=capture_dir,
            out_dir=out1,
            odds_source="none",
            prefer_pro=False,
        )
        config2 = PipelineConfig(
            date_local=TEST_DATE,
            capture_dir=capture_dir,
            out_dir=out2,
            odds_source="none",
            prefer_pro=False,
        )

        result1 = run_pipeline(config1)
        result2 = run_pipeline(config2)

        # Same number of stake cards
        assert len(result1.stake_card_paths) == len(result2.stake_card_paths)

        # Compare each stake card
        for p1, p2 in zip(sorted(result1.stake_card_paths), sorted(result2.stake_card_paths)):
            content1 = json.loads(p1.read_text())
            content2 = json.loads(p2.read_text())
            assert content1 == content2

    def test_pipeline_meeting_ordering(self, tmp_path: Path) -> None:
        """Test that meetings are processed in deterministic order."""
        capture_dir = tmp_path / "raw"
        shutil.copytree(RA_FIXTURES, capture_dir / "ra")
        out = tmp_path / "out"

        config = PipelineConfig(
            date_local=TEST_DATE,
            capture_dir=capture_dir,
            out_dir=out,
            odds_source="none",
            prefer_pro=False,
        )

        result = run_pipeline(config)

        meeting_ids = [m.meeting_id for m in result.meetings]
        assert meeting_ids == sorted(meeting_ids)

    def test_pipeline_no_errors_with_fixtures(self, tmp_path: Path) -> None:
        """Test pipeline runs without errors using fixtures."""
        capture_dir = tmp_path / "raw"
        shutil.copytree(RA_FIXTURES, capture_dir / "ra")
        out = tmp_path / "out"

        config = PipelineConfig(
            date_local=TEST_DATE,
            capture_dir=capture_dir,
            out_dir=out,
            odds_source="none",
            prefer_pro=False,
        )

        result = run_pipeline(config)

        assert len(result.errors) == 0
        assert len(result.stake_card_paths) > 0


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCollectStakeCardsCLI:
    def test_cli_help_shows_command(self) -> None:
        """Test that collect-stake-cards command appears in help."""
        from typer.testing import CliRunner

        from cli.turf_cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "collect-stake-cards" in result.output

    def test_cli_command_with_fixtures(self, tmp_path: Path) -> None:
        """Test CLI command runs successfully with fixtures."""
        from typer.testing import CliRunner

        from cli.turf_cli import app

        # Setup: copy fixtures to tmp capture dir
        capture_dir = tmp_path / "raw"
        shutil.copytree(RA_FIXTURES, capture_dir / "ra")
        out = tmp_path / "out"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "collect-stake-cards",
                "--date",
                TEST_DATE,
                "--capture-dir",
                str(capture_dir),
                "--out",
                str(out),
                "--odds-source",
                "none",
                "--no-prefer-pro",
            ],
        )

        assert result.exit_code == 0
        assert "stake card(s)" in result.output.lower() or "Generated" in result.output

        # Stake cards should exist
        stake_cards = list(out.rglob("stake_card_*.json"))
        assert len(stake_cards) > 0

    def test_cli_generates_digest(self, tmp_path: Path) -> None:
        """Test CLI generates daily digest alongside stake cards."""
        from typer.testing import CliRunner

        from cli.turf_cli import app

        capture_dir = tmp_path / "raw"
        shutil.copytree(RA_FIXTURES, capture_dir / "ra")
        out = tmp_path / "out"

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "collect-stake-cards",
                "--date",
                TEST_DATE,
                "--capture-dir",
                str(capture_dir),
                "--out",
                str(out),
                "--odds-source",
                "none",
                "--no-prefer-pro",
            ],
        )

        assert result.exit_code == 0

        # Digest should exist
        digest_path = out / "digests" / TEST_DATE / "daily_digest.json"
        assert digest_path.exists()

        digest = json.loads(digest_path.read_text())
        assert "meetings" in digest
        assert "counts" in digest


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_pipeline_with_odds_fixtures(self, tmp_path: Path) -> None:
        """Test full pipeline with both RA and odds fixtures."""
        capture_dir = tmp_path / "raw"
        shutil.copytree(RA_FIXTURES, capture_dir / "ra")
        out = tmp_path / "out"

        config = PipelineConfig(
            date_local=TEST_DATE,
            capture_dir=capture_dir,
            out_dir=out,
            odds_source="fixture",
            odds_fixtures_dir=ODDS_FIXTURES,
            prefer_pro=False,
        )

        result = run_pipeline(config)

        assert len(result.errors) == 0
        assert len(result.stake_card_paths) > 0

        # Verify odds were merged for race 1
        randwick_r1_path = out / TEST_DATE / TEST_MEETING / "stake_card_r1.json"
        assert randwick_r1_path.exists()

        stake_card = json.loads(randwick_r1_path.read_text())
        runners = stake_card["races"][0]["runners"]
        runner_a = next(r for r in runners if r["runner_name"] == "Fixture Horse A")
        # Should have odds from fixture (3.60) not RA (3.50)
        assert runner_a["odds_minimal"]["price_now_dec"] == 3.60

    def test_capture_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Test that capture and load are inverse operations."""
        # Capture from source fixture
        source_meeting = load_captured_meeting(RA_FIXTURES, TEST_DATE, TEST_MEETING)
        assert source_meeting is not None

        # Read HTMLs
        race_htmls = {}
        for race in source_meeting.races:
            race_htmls[race.race_number] = race.html_path.read_text()

        # Capture to tmp dir
        capture_dir = tmp_path / "captured"
        captured = capture_meeting(
            TEST_MEETING,
            TEST_DATE,
            race_htmls,
            capture_dir,
            captured_at="2025-12-18T10:00:00+11:00",
        )

        # Load back
        loaded = load_captured_meeting(capture_dir, TEST_DATE, TEST_MEETING)
        assert loaded is not None
        assert loaded.meeting_id == captured.meeting_id
        assert len(loaded.races) == len(captured.races)

        # Compare race HTML contents
        for orig_race, loaded_race in zip(source_meeting.races, loaded.races):
            assert orig_race.html_path.read_text() == loaded_race.html_path.read_text()

    def test_stake_card_runner_number_preserved(self, tmp_path: Path) -> None:
        """Test that runner_number is preserved through the entire pipeline."""
        capture_dir = tmp_path / "raw"
        shutil.copytree(RA_FIXTURES, capture_dir / "ra")
        out = tmp_path / "out"

        config = PipelineConfig(
            date_local=TEST_DATE,
            capture_dir=capture_dir,
            out_dir=out,
            odds_source="none",
            prefer_pro=False,
        )

        result = run_pipeline(config)
        assert len(result.stake_card_paths) > 0

        # Check a stake card
        randwick_r1_path = out / TEST_DATE / TEST_MEETING / "stake_card_r1.json"
        stake_card = json.loads(randwick_r1_path.read_text())
        runners = stake_card["races"][0]["runners"]

        # Verify runner numbers 1-4 are present
        runner_numbers = {r["runner_number"] for r in runners}
        assert runner_numbers == {1, 2, 3, 4}

        # Verify names match original
        expected_names = {
            1: "Fixture Horse A",
            2: "Fixture Horse B",
            3: "Fixture Horse C",
            4: "Fixture Horse D",
        }
        for r in runners:
            assert r["runner_name"] == expected_names[r["runner_number"]]
