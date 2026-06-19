#!/usr/bin/env python3
"""calibration.py — Layer 6: Self-update — recalibrate thresholds from override feedback.

Reads the override history and proposes new confidence thresholds for the
Critic Engine. This is the empirical calibration loop described in ADR-0021.

Outputs:
- New threshold values (reject/review)
- A calibration report (markdown)
- Optionally writes the new thresholds to a config file the Critic Engine can read

Usage:
    python3 calibration.py <history.json> [--output report.md] [--apply]
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# --- Default thresholds (MUST match critic_v2.py TIER_REJECT / TIER_REVIEW) ---
DEFAULT_REJECT = 0.6
DEFAULT_REVIEW = 0.7
KILL_SWITCH_RATE = 0.30

# --- Calibration targets ---
TARGET_PRECISION_ACCEPT = 0.90  # we want >= 90% of accept-tier findings to be correct


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def analyze_overrides(history: dict) -> dict:
    """Compute override statistics grouped by confidence bucket.

    Buckets: [0.0-0.4, 0.4-0.7, 0.7-0.9, 0.9-1.0]
    """
    overrides = history.get("overrides", [])
    resolutions = history.get("resolutions", [])
    # Group overrides by action and bucket
    by_bucket = defaultdict(lambda: {"accept_override": 0, "reject_override": 0, "confirm": 0, "total": 0})
    for o in overrides:
        conf = o.get("original_confidence", 0.5)
        if conf < 0.4:
            bucket = "0.0-0.4"
        elif conf < 0.7:
            bucket = "0.4-0.7"
        elif conf < 0.9:
            bucket = "0.7-0.9"
        else:
            bucket = "0.9-1.0"
        action = o.get("action", "unknown")
        by_bucket[bucket][action] = by_bucket[bucket].get(action, 0) + 1
        by_bucket[bucket]["total"] += 1
    # Compute precision per bucket
    for bucket, stats in by_bucket.items():
        if stats["total"] > 0:
            # Precision proxy: confirmed / (confirmed + reject_override)
            confirmed = stats.get("confirm", 0) + stats.get("accept_override", 0)
            wrong = stats.get("reject_override", 0)
            stats["precision_proxy"] = confirmed / (confirmed + wrong) if (confirmed + wrong) > 0 else None
    return dict(by_bucket)


def propose_thresholds(by_bucket: dict, target_precision: float = TARGET_PRECISION_ACCEPT) -> dict:
    """Propose new confidence thresholds based on bucket precision.

    Strategy (matches the code below — keep them in sync):
    - If bucket [0.0-0.4] is large and its precision_proxy < target, nudge the
      reject threshold down (the low tier already filters well; widen review).
    - If bucket [0.4-0.7] precision_proxy < target, tighten the review threshold.
    - If bucket [0.9-1.0] precision_proxy < target, emit a WARNING: even the
      accept tier is unreliable (no automatic threshold change is safe).
    """
    new_reject = DEFAULT_REJECT
    new_review = DEFAULT_REVIEW
    rationale = []
    # Low bucket: if precision is too low, the reject threshold is too lax
    low = by_bucket.get("0.0-0.4", {})
    if low.get("precision_proxy") is not None and low["precision_proxy"] < target_precision and low.get("total", 0) > 5:
        new_reject = max(0.2, DEFAULT_REJECT - 0.1)
        rationale.append(f"Lower reject threshold {DEFAULT_REJECT}->{new_reject} (low-bucket precision {low['precision_proxy']:.2f} < {target_precision})")
    # Mid bucket: precision determines the review threshold
    mid = by_bucket.get("0.4-0.7", {})
    if mid.get("precision_proxy") is not None and mid["total"] > 5:
        if mid["precision_proxy"] < target_precision:
            new_review = min(0.9, max(0.5, mid["precision_proxy"] + 0.1))
            rationale.append(f"Lower review threshold {DEFAULT_REVIEW}->{new_review} (mid-bucket precision {mid['precision_proxy']:.2f} < {target_precision})")
    # High bucket: if precision is low, even our "accept" tier has false positives
    high = by_bucket.get("0.9-1.0", {})
    if high.get("precision_proxy") is not None and high["precision_proxy"] < target_precision and high.get("total", 0) > 5:
        rationale.append(f"WARNING: high-bucket precision {high['precision_proxy']:.2f} < {target_precision} — even accept-tier is unreliable")
    if not rationale:
        rationale.append("No change: current thresholds are well-calibrated")
    return {
        "reject_below": round(new_reject, 2),
        "review_below": round(new_review, 2),
        "rationale": rationale,
    }


def generate_report(history_path: Path, by_bucket: dict, proposal: dict) -> str:
    md = [f"# Anti-Debt Calibration Report", f"", f"- **Generated**: {_now()}",
          f"- **Source**: `{history_path}`", f"- **Overrides analyzed**: {sum(s.get('total', 0) for s in by_bucket.values())}",
          f"", f"## Current vs proposed thresholds", f"", f"| Tier | Current | Proposed |", f"|------|---------|----------|",
          f"| Reject (below) | {DEFAULT_REJECT} | {proposal['reject_below']} |",
          f"| Review (below) | {DEFAULT_REVIEW} | {proposal['review_below']} |",
          f"", f"## Precision by confidence bucket", f"", f"| Bucket | Total | Accept-override | Reject-override | Confirm | Precision proxy |",
          f"|--------|------:|----------------:|----------------:|--------:|---------------:|"]
    for bucket in ["0.0-0.4", "0.4-0.7", "0.7-0.9", "0.9-1.0"]:
        s = by_bucket.get(bucket, {})
        pp = s.get("precision_proxy")
        pp_str = f"{pp:.2f}" if pp is not None else "n/a"
        md.append(f"| {bucket} | {s.get('total', 0)} | {s.get('accept_override', 0)} | {s.get('reject_override', 0)} | {s.get('confirm', 0)} | {pp_str} |")
    md.append("")
    md.append("## Rationale")
    for r in proposal["rationale"]:
        md.append(f"- {r}")
    return "\n".join(md)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("history", help="Path to .debt-history.json")
    parser.add_argument("--output", default=None, help="Output markdown report path")
    parser.add_argument("--apply", action="store_true", help="Write proposed thresholds to critic_config.json")
    args = parser.parse_args()
    history_path = Path(args.history)
    if not history_path.exists():
        print(json.dumps({"error": f"history not found: {history_path}"}))
        return 1
    history = json.loads(history_path.read_text(encoding="utf-8"))
    by_bucket = analyze_overrides(history)
    proposal = propose_thresholds(by_bucket)
    report = generate_report(history_path, by_bucket, proposal)
    out_path = Path(args.output) if args.output else history_path.parent / "calibration_report.md"
    out_path.write_text(report, encoding="utf-8")
    if args.apply:
        config_path = history_path.parent / "critic_config.json"
        config_path.write_text(json.dumps({
            "version": "1.0.0",
            "thresholds": {
                "reject_below": proposal["reject_below"],
                "review_below": proposal["review_below"],
            },
            "applied_at": _now(),
            "rationale": proposal["rationale"],
        }, indent=2), encoding="utf-8")
        print(json.dumps({"config_written": str(config_path), "thresholds": proposal}))
        return 0
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
