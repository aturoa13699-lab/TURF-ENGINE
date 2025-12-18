from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_runs(path: Path) -> None:
    rows = [
        {
            "meeting_id": "M1",
            "race_number": 1,
            "runner_number": 1,
            "win_prob": 0.4,
            "outcome": 1,
            "price_now_dec": 3.0,
            "value_edge": 0.05,
        },
        {
            "meeting_id": "M1",
            "race_number": 1,
            "runner_number": 2,
            "win_prob": 0.2,
            "outcome": 0,
            "price_now_dec": 6.0,
            "value_edge": -0.01,
        },
    ]
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row))
            f.write("\n")


def test_analyze_backtest_outputs(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    runs_path = tmp_path / "runs.jsonl"
    out_dir = tmp_path / "out"

    metrics = {
        "count": 2,
        "brier": 0.18,
        "logloss": 0.5,
        "roi": 0.25,
        "roi_sample_size": 1,
        "avg_edge": 0.02,
        "start_date": "2025-01-01",
        "end_date": "2025-01-07",
        "model": "lite",
    }

    metrics_path.write_text(json.dumps(metrics))
    _write_runs(runs_path)

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "tools.analyze_backtest",
            "--metrics",
            str(metrics_path),
            "--runs",
            str(runs_path),
            "--out",
            str(out_dir),
        ]
    )

    report = (out_dir / "report.md").read_text()
    patch_candidates = (out_dir / "patch_candidates.md").read_text()
    metrics_summary = json.loads((out_dir / "metrics_summary.json").read_text())

    assert "Weekly Backtest Report" in report
    assert "Patch candidates" in report
    assert "Patch candidates" in patch_candidates
    assert metrics_summary.get("metrics", {}).get("count") == 2
    assert (out_dir / "loss_clusters.json").exists()
    assert (out_dir / "experiments.yml").exists()

