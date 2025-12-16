"""Analyze backtest results and generate improvement recommendations.

Reads backtest metrics and generates a markdown report with:
- Performance summary
- Calibration analysis
- Loss clusters identification
- Ranked patch candidates (recommendations, not auto-changes)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def load_metrics(metrics_path: Path) -> Dict[str, Any]:
    """Load backtest metrics from JSON file."""
    if not metrics_path.exists():
        return {}
    return json.loads(metrics_path.read_text())


def analyze_performance(metrics: Dict[str, Any]) -> List[str]:
    """Generate performance analysis insights."""
    insights = []

    count = metrics.get("count", 0)
    if count == 0:
        return ["⚠️ No data points in backtest period"]

    insights.append(f"**Sample size:** {count} predictions")

    # Brier score analysis
    brier = metrics.get("brier")
    if brier is not None:
        if brier < 0.2:
            insights.append(f"✅ Brier score: {brier:.4f} (good calibration)")
        elif brier < 0.25:
            insights.append(f"⚠️ Brier score: {brier:.4f} (acceptable)")
        else:
            insights.append(f"❌ Brier score: {brier:.4f} (needs improvement)")

    # Log loss analysis
    logloss = metrics.get("logloss")
    if logloss is not None:
        if logloss < 0.6:
            insights.append(f"✅ Log loss: {logloss:.4f} (good)")
        elif logloss < 0.7:
            insights.append(f"⚠️ Log loss: {logloss:.4f} (acceptable)")
        else:
            insights.append(f"❌ Log loss: {logloss:.4f} (high)")

    # ROI analysis
    roi = metrics.get("roi")
    roi_sample = metrics.get("roi_sample_size", 0)
    if roi is not None and roi_sample > 0:
        roi_pct = roi * 100
        if roi > 0:
            insights.append(f"✅ ROI: {roi_pct:+.2f}% on {roi_sample} bets")
        else:
            insights.append(f"❌ ROI: {roi_pct:+.2f}% on {roi_sample} bets")

    return insights


def generate_patch_candidates(metrics: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generate ranked improvement recommendations based on metrics.

    These are suggestions for manual review, NOT auto-applied changes.
    """
    candidates = []

    brier = metrics.get("brier")
    logloss = metrics.get("logloss")
    roi = metrics.get("roi")
    count = metrics.get("count", 0)

    # Low sample size
    if count < 50:
        candidates.append({
            "priority": "HIGH",
            "category": "Data",
            "suggestion": "Increase backtest period or data coverage",
            "rationale": f"Only {count} samples - insufficient for statistical significance"
        })

    # Calibration issues
    if brier is not None and brier > 0.25:
        candidates.append({
            "priority": "HIGH",
            "category": "Calibration",
            "suggestion": "Review probability estimation methodology",
            "rationale": f"Brier score {brier:.4f} indicates poor calibration"
        })

    # High log loss
    if logloss is not None and logloss > 0.7:
        candidates.append({
            "priority": "MEDIUM",
            "category": "Model",
            "suggestion": "Investigate extreme probability predictions",
            "rationale": f"Log loss {logloss:.4f} suggests over-confident predictions"
        })

    # Negative ROI
    if roi is not None and roi < 0:
        candidates.append({
            "priority": "MEDIUM",
            "category": "Staking",
            "suggestion": "Review value edge threshold (currently 2%)",
            "rationale": f"ROI is negative ({roi*100:.2f}%) - edge threshold may be too low"
        })

    # Positive ROI but low sample
    roi_sample = metrics.get("roi_sample_size", 0)
    if roi is not None and roi > 0.1 and roi_sample < 20:
        candidates.append({
            "priority": "LOW",
            "category": "Validation",
            "suggestion": "Extend backtest period to validate ROI",
            "rationale": f"Good ROI ({roi*100:.2f}%) but only {roi_sample} bets - may be luck"
        })

    return candidates


def generate_report(metrics: Dict[str, Any], output_path: Path) -> str:
    """Generate markdown report from backtest metrics."""
    lines = [
        "# Weekly Backtest Analysis Report",
        "",
        f"**Generated:** {datetime.utcnow().isoformat()}Z",
        "",
        "---",
        "",
        "## Performance Summary",
        "",
    ]

    # Performance insights
    insights = analyze_performance(metrics)
    for insight in insights:
        lines.append(f"- {insight}")

    lines.extend([
        "",
        "---",
        "",
        "## Raw Metrics",
        "",
        "```json",
        json.dumps(metrics, indent=2),
        "```",
        "",
        "---",
        "",
        "## Improvement Recommendations",
        "",
        "*These are suggestions for manual review. Lite model ordering/math is NOT auto-changed.*",
        "",
    ])

    # Patch candidates
    candidates = generate_patch_candidates(metrics)
    if not candidates:
        lines.append("✅ No critical issues identified.")
    else:
        for i, candidate in enumerate(candidates, 1):
            lines.extend([
                f"### {i}. [{candidate['priority']}] {candidate['category']}",
                "",
                f"**Suggestion:** {candidate['suggestion']}",
                "",
                f"**Rationale:** {candidate['rationale']}",
                "",
            ])

    lines.extend([
        "---",
        "",
        "## Next Steps",
        "",
        "- [ ] Review recommendations above",
        "- [ ] Check data completeness for the backtest period",
        "- [ ] Compare with previous week's metrics",
        "- [ ] Document any changes made based on this report",
        "",
    ])

    report = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze backtest results and generate report")
    parser.add_argument("--metrics", type=Path, required=True, help="Path to backtest_metrics.json")
    parser.add_argument("--out", type=Path, default=Path("out/reports/backtest_report.md"), help="Output report path")
    args = parser.parse_args()

    metrics = load_metrics(args.metrics)
    report = generate_report(metrics, args.out)
    print(f"Report written to {args.out}")
    print("\n--- Report Preview ---\n")
    print(report[:1000] + "..." if len(report) > 1000 else report)


if __name__ == "__main__":
    main()
