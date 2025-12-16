"""Tests for CLI extensions: value filter and matchups."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from turf.cli import (
    app,
    calculate_ev,
    calculate_pairwise_probability,
    logit,
    sigmoid,
)

runner = CliRunner()


class TestEVCalculation:
    """Tests for expected value calculation."""

    def test_positive_ev(self):
        """Positive EV when probability exceeds implied probability."""
        # 50% chance at 2.5 odds = 50% * 2.5 - 1 = 0.25 (25% EV)
        ev = calculate_ev(0.5, 2.5)
        assert ev == pytest.approx(0.25)

    def test_negative_ev(self):
        """Negative EV when probability below implied probability."""
        # 30% chance at 2.0 odds = 30% * 2.0 - 1 = -0.4 (-40% EV)
        ev = calculate_ev(0.3, 2.0)
        assert ev == pytest.approx(-0.4)

    def test_zero_ev(self):
        """Zero EV at fair odds."""
        # 50% chance at 2.0 odds = 50% * 2.0 - 1 = 0 (fair)
        ev = calculate_ev(0.5, 2.0)
        assert ev == pytest.approx(0.0)

    def test_invalid_inputs(self):
        """Invalid inputs return negative infinity."""
        assert calculate_ev(0, 2.0) == float("-inf")
        assert calculate_ev(0.5, 1.0) == float("-inf")
        assert calculate_ev(-0.1, 2.0) == float("-inf")


class TestMathFunctions:
    """Tests for mathematical helper functions."""

    def test_sigmoid(self):
        """Sigmoid function properties."""
        assert sigmoid(0) == pytest.approx(0.5)
        assert sigmoid(100) == pytest.approx(1.0)
        assert sigmoid(-100) == pytest.approx(0.0)
        # Symmetry
        assert sigmoid(2) + sigmoid(-2) == pytest.approx(1.0)

    def test_logit(self):
        """Logit function properties."""
        assert logit(0.5) == pytest.approx(0.0)
        assert logit(0.73105) == pytest.approx(1.0, rel=0.01)
        assert logit(0.26894) == pytest.approx(-1.0, rel=0.01)

    def test_pairwise_probability_symmetry(self):
        """P(A beats B) + P(B beats A) = 1."""
        p_a_beats_b = calculate_pairwise_probability(0.4, 0.3)
        p_b_beats_a = calculate_pairwise_probability(0.3, 0.4)
        assert p_a_beats_b + p_b_beats_a == pytest.approx(1.0)

    def test_pairwise_equal_probabilities(self):
        """Equal probabilities give 50-50 matchup."""
        assert calculate_pairwise_probability(0.3, 0.3) == pytest.approx(0.5)

    def test_pairwise_dominant(self):
        """Higher probability should dominate matchup."""
        p = calculate_pairwise_probability(0.6, 0.2)
        assert p > 0.5  # Higher prob runner should have >50% head-to-head


class TestValueFilterCLI:
    """Tests for value bet filtering via CLI."""

    @pytest.fixture
    def sample_stake_card(self, tmp_path):
        """Create a sample stake card for testing."""
        card = {
            "meeting": {"meeting_id": "TEST_001"},
            "races": [{
                "race_number": 1,
                "runners": [
                    {
                        "runner_number": 1,
                        "runner_name": "Good Value",
                        "lite_tag": "A_LITE",
                        "lite_score": 0.7,
                        "odds_minimal": {"price_now_dec": 3.0},
                        "forecast": {"win_prob": 0.5},  # EV = 0.5 * 3 - 1 = 0.5 (50%)
                    },
                    {
                        "runner_number": 2,
                        "runner_name": "No Value",
                        "lite_tag": "B_LITE",
                        "lite_score": 0.5,
                        "odds_minimal": {"price_now_dec": 5.0},
                        "forecast": {"win_prob": 0.1},  # EV = 0.1 * 5 - 1 = -0.5 (-50%)
                    },
                    {
                        "runner_number": 3,
                        "runner_name": "Marginal",
                        "lite_tag": "PASS_LITE",
                        "lite_score": 0.3,
                        "odds_minimal": {"price_now_dec": 2.0},
                        "forecast": {"win_prob": 0.55},  # EV = 0.55 * 2 - 1 = 0.1 (10%)
                    },
                ],
            }],
        }

        path = tmp_path / "stake_card.json"
        path.write_text(json.dumps(card))
        return path

    def test_filter_cli_runs(self, sample_stake_card, tmp_path):
        """CLI filter command runs successfully."""
        out_path = tmp_path / "value_bets.json"
        result = runner.invoke(
            app,
            ["filter", "value", "--stake-card", str(sample_stake_card), "--out", str(out_path), "-q"]
        )
        assert result.exit_code == 0
        assert out_path.exists()

        data = json.loads(out_path.read_text())
        # Should find runners 1 (50% EV) and 3 (10% EV), not runner 2 (-50%)
        assert data["count"] == 2

    def test_filter_cli_with_price_limit(self, sample_stake_card, tmp_path):
        """CLI filter respects price limits."""
        out_path = tmp_path / "value_bets.json"
        result = runner.invoke(
            app,
            ["filter", "value", "--stake-card", str(sample_stake_card), "--max-price", "2.5", "--min-ev", "0", "--out", str(out_path), "-q"]
        )
        assert result.exit_code == 0

        data = json.loads(out_path.read_text())
        # Only runner 3 has price <= 2.5 and positive EV
        assert data["count"] == 1
        assert data["bets"][0]["runner_number"] == 3


class TestMatchupsCLI:
    """Tests for head-to-head matchup generation via CLI."""

    @pytest.fixture
    def sample_stake_card(self, tmp_path):
        """Create a sample stake card for testing."""
        card = {
            "meeting": {"meeting_id": "TEST_002"},
            "races": [{
                "race_number": 1,
                "runners": [
                    {"runner_number": 1, "runner_name": "Favorite", "forecast": {"win_prob": 0.4}},
                    {"runner_number": 2, "runner_name": "Second", "forecast": {"win_prob": 0.25}},
                    {"runner_number": 3, "runner_name": "Outsider", "forecast": {"win_prob": 0.15}},
                ],
            }],
        }

        path = tmp_path / "stake_card.json"
        path.write_text(json.dumps(card))
        return path

    def test_matchups_cli_runs(self, sample_stake_card, tmp_path):
        """CLI matchups command runs successfully."""
        out_path = tmp_path / "matchups.json"
        result = runner.invoke(
            app,
            ["matchups", "generate", "--stake-card", str(sample_stake_card), "--out", str(out_path), "-q"]
        )
        assert result.exit_code == 0
        assert out_path.exists()

    def test_matchups_cli_output(self, sample_stake_card, tmp_path):
        """CLI matchups produces correct output."""
        out_path = tmp_path / "matchups.json"
        runner.invoke(
            app,
            ["matchups", "generate", "--stake-card", str(sample_stake_card), "--top", "3", "--out", str(out_path), "-q"]
        )

        data = json.loads(out_path.read_text())
        assert data["method"] == "bradley_terry"
        # 3 runners = 3 pairs
        assert data["matchup_count"] == 3

        # Check symmetry
        for matchup in data["matchups"]:
            total = matchup["p_a_beats_b"] + matchup["p_b_beats_a"]
            assert total == pytest.approx(1.0)
