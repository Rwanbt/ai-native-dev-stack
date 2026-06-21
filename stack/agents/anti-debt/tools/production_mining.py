#!/usr/bin/env python3
"""production_mining.py — Extract eval datasets from production scan history.

Transforms real .debt-history.json files (with human overrides) into labeled
test cases for the eval pipeline.

Labels come from human overrides:
  - accept_override → finding was correct (true positive)
  - reject_override → finding was wrong (false positive)
  - confirm → finding verified correct (true positive, high confidence)

Usage:
    python production_mining.py --history path/to/.debt-history.json --output tests/corpus/production/
    python production_mining.py --history-dir /path/to/projects/ --output tests/corpus/production/
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def extract_overrides(history: dict) -> list[dict]:
    """Extract labeled examples from override records in history."""
    overrides = history.get("overrides", [])
    labeled = []
    for ov in overrides:
        action = ov.get("action", "")
        if action not in ("accept_override", "reject_override", "confirm"):
            continue

        if action == "reject_override":
            expected_verdict = "reject"
        else:
            expected_verdict = "accept"

        labeled.append({
            "finding_id": ov.get("finding_id", ""),
            "expected_verdict": expected_verdict,
            "original_confidence": ov.get("original_confidence", 0.0),
            "reason": ov.get("reason", ""),
            "override_action": action,
            "timestamp": ov.get("timestamp", ""),
        })
    return labeled


def enrich_with_findings(labeled: list[dict], history: dict) -> list[dict]:
    """Attach the original finding data to each labeled example."""
    findings_by_id = {}
    for scan in history.get("scans", []):
        for f in scan.get("findings", []):
            findings_by_id[f.get("id", "")] = f

    enriched = []
    for item in labeled:
        fid = item["finding_id"]
        finding = findings_by_id.get(fid)
        if finding:
            enriched.append({
                "input": finding,
                "expected_verdict": item["expected_verdict"],
                "reason": item["reason"],
                "original_confidence": item["original_confidence"],
                "override_action": item["override_action"],
                "timestamp": item["timestamp"],
                "provenance": {
                    "source": "production_override",
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                },
            })
        else:
            enriched.append({
                "input": {"id": fid, "_note": "finding not found in scans"},
                "expected_verdict": item["expected_verdict"],
                "reason": item["reason"],
                "original_confidence": item["original_confidence"],
                "override_action": item["override_action"],
                "timestamp": item["timestamp"],
                "provenance": {
                    "source": "production_override",
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                    "warning": "original finding not found in scan history",
                },
            })
    return enriched


def compute_stats(dataset: list[dict]) -> dict:
    """Compute distribution statistics for the mined dataset."""
    verdicts = Counter(item["expected_verdict"] for item in dataset)
    categories = Counter(
        item["input"].get("category", "unknown") for item in dataset
    )
    severities = Counter(
        item["input"].get("severity", "unknown") for item in dataset
    )
    confidence_buckets = Counter()
    for item in dataset:
        c = item["original_confidence"]
        if c < 0.4:
            confidence_buckets["[0.0-0.4)"] += 1
        elif c < 0.7:
            confidence_buckets["[0.4-0.7)"] += 1
        elif c < 0.9:
            confidence_buckets["[0.7-0.9)"] += 1
        else:
            confidence_buckets["[0.9-1.0]"] += 1

    return {
        "total": len(dataset),
        "by_verdict": dict(verdicts),
        "by_category": dict(categories),
        "by_severity": dict(severities),
        "by_confidence_bucket": dict(confidence_buckets),
    }


def mine_history_file(history_path: Path) -> list[dict]:
    """Mine a single history file into labeled examples."""
    with open(history_path, "r", encoding="utf-8") as f:
        history = json.load(f)
    labeled = extract_overrides(history)
    return enrich_with_findings(labeled, history)


def mine_directory(dir_path: Path) -> list[dict]:
    """Find all .debt-history.json files in a directory tree and mine them."""
    all_examples = []
    for hist_file in dir_path.rglob(".debt-history.json"):
        examples = mine_history_file(hist_file)
        all_examples.extend(examples)
    return all_examples


def write_dataset(dataset: list[dict], output_dir: Path, name: str = "mined") -> Path:
    """Write dataset to output directory with timestamp."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"{name}-{ts}.json"
    output_path = output_dir / filename

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "production_mining.py",
            "total_examples": len(dataset),
        },
        "stats": compute_stats(dataset),
        "examples": dataset,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Mine production data into eval datasets")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--history", type=Path, help="Single .debt-history.json file")
    group.add_argument("--history-dir", type=Path, help="Directory to search for .debt-history.json files")
    parser.add_argument("--output", type=Path, default=Path("tests/corpus/production"),
                        help="Output directory for mined datasets")
    parser.add_argument("--name", default="mined", help="Dataset name prefix")
    args = parser.parse_args()

    if args.history:
        if not args.history.exists():
            print(f"ERROR: {args.history} not found", file=sys.stderr)
            sys.exit(1)
        dataset = mine_history_file(args.history)
    else:
        if not args.history_dir.exists():
            print(f"ERROR: {args.history_dir} not found", file=sys.stderr)
            sys.exit(1)
        dataset = mine_directory(args.history_dir)

    if not dataset:
        print("No override data found — dataset is empty.")
        print("Overrides are recorded via: critic_v2.py override <history> <id> <action> <reason>")
        sys.exit(0)

    output_path = write_dataset(dataset, args.output, args.name)
    stats = compute_stats(dataset)

    print(f"Mined {stats['total']} labeled examples → {output_path}")
    print(f"  Verdicts: {stats['by_verdict']}")
    print(f"  Categories: {stats['by_category']}")
    print(f"  Severities: {stats['by_severity']}")
    print(f"  Confidence buckets: {stats['by_confidence_bucket']}")


if __name__ == "__main__":
    main()
