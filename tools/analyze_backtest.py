from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

BUCKETS: List[Tuple[str, float, float | None]] = [
    ("<=2.0", 0.0, 2.0),
    ("2-5", 2.0, 5.0),
    ("5-10", 5.0, 10.0),
    (">10", 10.0, None),
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def load_runs(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def bucket_for_price(price: Any) -> str:
    try:
        p = float(price)
    except (TypeError, ValueError):
        return "unknown"
    for label, low, high in BUCKETS:
        if high is None and p >= low:
            return label
        if p >= low and p < high:  # noqa: PLC1901
            return label
    return "unknown"


def summarise_buckets(runs: Iterable[dict]) -> List[dict]:
    stats: Dict[str, Dict[str, float | int]] = {}
    for row in runs:
        bucket = bucket_for_price(row.get("price_now_dec"))
        bucket_stats = stats.setdefault(
            bucket,
            {"count": 0, "wins": 0, "roi_sum": 0.0, "roi_count": 0, "avg_prob_sum": 0.0},
        )
        outcome = 1 if row.get("outcome") else 0
        price = row.get("price_now_dec")
        prob = row.get("win_prob")
        bucket_stats["count"] += 1
        bucket_stats["wins"] += outcome
        if prob is not None:
            bucket_stats["avg_prob_sum"] += float(prob)
        if price is not None:
            try:
                p_val = float(price)
                roi = (p_val - 1.0) if outcome else -1.0
                bucket_stats["roi_sum"] += roi
                bucket_stats["roi_count"] += 1
            except (TypeError, ValueError):
                pass
    bucket_list: List[dict] = []
    for bucket, values in stats.items():
        count = int(values.get("count", 0))
        roi_count = int(values.get("roi_count", 0))
        roi_avg = values["roi_sum"] / roi_count if roi_count else None
        avg_prob = values["avg_prob_sum"] / count if count else None
        bucket_list.append(
            {
                "bucket": bucket,
                "count": count,
                "wins": int(values.get("wins", 0)),
                "roi": roi_avg,
                "roi_sample_size": roi_count,
                "avg_prob": avg_prob,
            }
        )
    bucket_list.sort(key=lambda x: x["bucket"])
    return bucket_list


def build_patch_candidates(metrics: dict, buckets: List[dict]) -> List[dict]:
    candidates: List[dict] = []
    roi = metrics.get("roi")
    logloss = metrics.get("logloss")
    sample_size = metrics.get("roi_sample_size") or 0
    count = metrics.get("count") or 0

    if roi is None or count == 0:
        candidates.append(
            {
                "title": "Insufficient data for ROI",
                "segment": "global",
                "evidence": f"count={count}",
                "suggestion": "Increase sample size or ensure backtest window has populated forecasts/results.",
            }
        )
    elif roi < 0:
        candidates.append(
            {
                "title": "ROI negative — calibration/overlay review",
                "segment": "global",
                "evidence": f"roi={roi:.3f}, sample_size={sample_size}",
                "suggestion": "Review pricing calibration or add conservative overlay for negative expected value segments.",
            }
        )
    elif roi < 0.02:
        candidates.append(
            {
                "title": "ROI flat — consider risk/edge weighting",
                "segment": "global",
                "evidence": f"roi={roi:.3f}, sample_size={sample_size}",
                "suggestion": "Evaluate edge-weighted or capped staking to improve risk-adjusted returns.",
            }
        )

    if logloss is not None and logloss > 0.7:
        candidates.append(
            {
                "title": "Calibration drift (logloss high)",
                "segment": "global",
                "evidence": f"logloss={logloss:.3f}",
                "suggestion": "Check probability calibration or feature drift; consider recalibration on recent data.",
            }
        )

    negative_buckets = [b for b in buckets if b.get("roi") is not None and b.get("roi", 0) < 0]
    negative_buckets.sort(key=lambda x: (x.get("roi") or 0))
    for bucket in negative_buckets[:3]:
        candidates.append(
            {
                "title": "Bucket underperforming",
                "segment": f"price={bucket['bucket']}",
                "evidence": f"roi={bucket.get('roi')}, count={bucket.get('count')}",
                "suggestion": "Review pricing/edge assumptions for this odds bucket; consider overlay or exclusion rules.",
            }
        )

    return candidates


def write_patch_candidates_md(path: Path, candidates: List[dict]) -> None:
    lines = ["# Patch candidates", ""]
    if not candidates:
        lines.append("No patch candidates generated (insufficient data).")
    else:
        for idx, cand in enumerate(candidates, start=1):
            lines.append(f"{idx}. **{cand['title']}** — {cand['suggestion']} ({cand['evidence']})")
    path.write_text("\n".join(lines))


def write_experiments_yaml(path: Path, candidates: List[dict]) -> None:
    lines = ["experiments:"]
    for idx, cand in enumerate(candidates, start=1):
        lines.append(f"  - id: exp_{idx:02d}")
        lines.append(f"    title: \"{cand['title']}\"")
        lines.append(f"    segment: \"{cand['segment']}\"")
        lines.append(f"    evidence: \"{cand['evidence']}\"")
        lines.append(f"    suggestion: \"{cand['suggestion']}\"")
    if len(lines) == 1:
        lines.append("  - id: exp_01")
        lines.append("    title: \"No experiments generated\"")
        lines.append("    suggestion: \"Add backtest data to produce patch candidates.\"")
    path.write_text("\n".join(lines))


def write_loss_clusters(path: Path, buckets: List[dict]) -> None:
    loss_clusters = [b for b in buckets if b.get("roi") is not None and b.get("roi") < 0]
    loss_clusters.sort(key=lambda x: (x.get("roi") or 0))
    path.write_text(json.dumps(loss_clusters, indent=2))


def write_report_md(path: Path, metrics: dict, buckets: List[dict], candidates: List[dict]) -> None:
    lines = ["# Weekly Backtest Report", ""]
    lines.append(f"Generated at (UTC): {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    for field in ("start_date", "end_date", "model", "git_sha"):
        if metrics.get(field) is not None:
            lines.append(f"- {field.replace('_', ' ').title()}: {metrics[field]}")
    lines.append("")

    lines.append("## Metrics")
    if metrics:
        for key in ("count", "brier", "logloss", "roi", "roi_sample_size", "avg_edge"):
            if key in metrics:
                lines.append(f"- {key}: {metrics.get(key)}")
    else:
        lines.append("- (no metrics available)")
    lines.append("")

    lines.append("## Buckets")
    if buckets:
        for b in buckets:
            lines.append(
                f"- {b['bucket']}: count={b['count']}, roi={b['roi']}, roi_sample_size={b['roi_sample_size']}, avg_prob={b['avg_prob']}"
            )
    else:
        lines.append("- No bucket data available")
    lines.append("")

    lines.append("## Patch candidates")
    if candidates:
        for idx, cand in enumerate(candidates, start=1):
            lines.append(f"{idx}. **{cand['title']}** — {cand['suggestion']} ({cand['evidence']})")
    else:
        lines.append("- None (insufficient data)")
    lines.append("")

    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze backtest outputs and generate reports")
    parser.add_argument("--metrics", type=Path, default=Path("out/backtest/metrics.json"))
    parser.add_argument("--runs", type=Path, default=Path("out/backtest/runs.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("out/backtest"))
    args = parser.parse_args()

    metrics = load_json(args.metrics, default={})
    runs = load_runs(args.runs)
    buckets = summarise_buckets(runs) if runs else []
    candidates = build_patch_candidates(metrics, buckets)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.md").write_text("")

    metrics_summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_metrics": args.metrics.name,
        "source_runs": args.runs.name,
        "metrics": metrics,
        "buckets": buckets,
        "patch_candidates": [c.get("title") for c in candidates],
    }

    (args.out / "metrics_summary.json").write_text(json.dumps(metrics_summary, indent=2))
    write_patch_candidates_md(args.out / "patch_candidates.md", candidates)
    write_experiments_yaml(args.out / "experiments.yml", candidates)
    write_loss_clusters(args.out / "loss_clusters.json", buckets)
    write_report_md(args.out / "report.md", metrics, buckets, candidates)


if __name__ == "__main__":
    main()
