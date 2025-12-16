"""Golden determinism tests for TURF ENGINE LITE.

Ensures that for fixed inputs, the Lite model produces identical outputs.
This is critical for reproducibility and debugging.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from turf.compile_lite import RunnerInput, compile_stake_card


def hash_json(obj: dict) -> str:
    """Create deterministic hash of JSON-serializable object."""
    serialized = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


# Fixed test inputs for determinism check
FIXED_MEETING = {
    "meeting_id": "TEST_DETERMINISM_001",
    "track_canonical": "RANDWICK",
    "date_local": "2025-01-01",
}

FIXED_RACE = {
    "race_number": 1,
    "distance_m": 1200,
    "track_condition_raw": "Good",
}

FIXED_RUNNERS = [
    RunnerInput(
        runner_number=1,
        runner_name="DETERMINISTIC HORSE A",
        barrier=1,
        price_now_dec=3.50,
        map_role_inferred="LEADER",
        avg_speed_mps=16.5,
    ),
    RunnerInput(
        runner_number=2,
        runner_name="DETERMINISTIC HORSE B",
        barrier=5,
        price_now_dec=4.00,
        map_role_inferred="MIDFIELD",
        avg_speed_mps=16.2,
    ),
    RunnerInput(
        runner_number=3,
        runner_name="DETERMINISTIC HORSE C",
        barrier=8,
        price_now_dec=8.00,
        map_role_inferred="BACKMARKER",
        avg_speed_mps=15.8,
    ),
]


class TestLiteDeterminism:
    """Test that Lite model output is deterministic for fixed inputs."""

    def test_compile_stake_card_deterministic(self):
        """Same inputs should produce identical stake card output."""
        # Run twice with identical inputs
        card1, outputs1 = compile_stake_card(
            meeting=FIXED_MEETING,
            race=FIXED_RACE,
            runner_rows=FIXED_RUNNERS,
            captured_at="2025-01-01T10:00:00+11:00",
            include_overlay=False,
        )

        card2, outputs2 = compile_stake_card(
            meeting=FIXED_MEETING,
            race=FIXED_RACE,
            runner_rows=FIXED_RUNNERS,
            captured_at="2025-01-01T10:00:00+11:00",
            include_overlay=False,
        )

        # Hash both outputs
        hash1 = hash_json(card1)
        hash2 = hash_json(card2)

        assert hash1 == hash2, f"Non-deterministic output: {hash1} != {hash2}"

    def test_lite_scores_stable(self):
        """Lite scores should be identical across runs."""
        _, outputs1 = compile_stake_card(
            meeting=FIXED_MEETING,
            race=FIXED_RACE,
            runner_rows=FIXED_RUNNERS,
            captured_at="2025-01-01T10:00:00+11:00",
            include_overlay=False,
        )

        _, outputs2 = compile_stake_card(
            meeting=FIXED_MEETING,
            race=FIXED_RACE,
            runner_rows=FIXED_RUNNERS,
            captured_at="2025-01-01T10:00:00+11:00",
            include_overlay=False,
        )

        for o1, o2 in zip(outputs1, outputs2):
            assert o1.lite_score == o2.lite_score, (
                f"Runner {o1.runner_number}: score mismatch {o1.lite_score} != {o2.lite_score}"
            )
            assert o1.lite_tag == o2.lite_tag, (
                f"Runner {o1.runner_number}: tag mismatch {o1.lite_tag} != {o2.lite_tag}"
            )

    def test_runner_ordering_stable(self):
        """Runner ordering by lite_score should be consistent."""
        _, outputs1 = compile_stake_card(
            meeting=FIXED_MEETING,
            race=FIXED_RACE,
            runner_rows=FIXED_RUNNERS,
            captured_at="2025-01-01T10:00:00+11:00",
            include_overlay=False,
        )

        _, outputs2 = compile_stake_card(
            meeting=FIXED_MEETING,
            race=FIXED_RACE,
            runner_rows=FIXED_RUNNERS,
            captured_at="2025-01-01T10:00:00+11:00",
            include_overlay=False,
        )

        order1 = [o.runner_number for o in sorted(outputs1, key=lambda x: -x.lite_score)]
        order2 = [o.runner_number for o in sorted(outputs2, key=lambda x: -x.lite_score)]

        assert order1 == order2, f"Ordering mismatch: {order1} != {order2}"


class TestGoldenOutput:
    """Test against known golden outputs (regression tests)."""

    # Known good hash for the fixed inputs above
    # Update this when intentionally changing Lite algorithm
    GOLDEN_HASH = None  # Set to actual hash after first run

    def test_against_golden_hash(self):
        """Output should match known golden hash (if set)."""
        if self.GOLDEN_HASH is None:
            pytest.skip("No golden hash set - run once to establish baseline")

        card, _ = compile_stake_card(
            meeting=FIXED_MEETING,
            race=FIXED_RACE,
            runner_rows=FIXED_RUNNERS,
            captured_at="2025-01-01T10:00:00+11:00",
            include_overlay=False,
        )

        current_hash = hash_json(card)
        assert current_hash == self.GOLDEN_HASH, (
            f"Output changed from golden baseline!\n"
            f"Expected: {self.GOLDEN_HASH}\n"
            f"Got: {current_hash}\n"
            f"If this change is intentional, update GOLDEN_HASH."
        )
