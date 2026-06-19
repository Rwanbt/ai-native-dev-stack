#!/usr/bin/env python3
"""aggregate.py — Combine scan outputs into a unified .debt-scan.json.

Reads .debt-scan-tmp/*.json (produced by scan_code.py, scan_security.py, scan_deps.py)
and produces a single .debt-scan.json conforming to the schema.

Usage:
    python3 aggregate.py .debt-scan-tmp/ [output.json]
"""
from __future__ import annotations
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: aggregate.py <tmp-dir> [output.json]"}))
        return 1

    tmp_dir = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".debt-scan.json")

    if not tmp_dir.is_dir():
        print(json.dumps({"error": f"not a directory: {tmp_dir}"}))
        return 1

    all_findings = []
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    by_category = {}
    warnings = []

    for scan_file in sorted(tmp_dir.glob("*.json")):
        try:
            data = json.loads(scan_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            warnings.append({"warning": f"failed to read {scan_file}: {e}"})
            continue

        findings = data.get("findings", [])
        for f in findings:
            if "warning" in f:
                warnings.append(f)
                continue
            # Validate minimum structure
            for required in ("category", "severity", "evidence", "confidence"):
                if required not in f:
                    warnings.append({"warning": f"finding missing {required} in {scan_file.name}"})
                    break
            else:
                all_findings.append(f)
                sev = f.get("severity", "low")
                by_severity[sev] = by_severity.get(sev, 0) + 1
                cat = f.get("category", "unknown")
                by_category[cat] = by_category.get(cat, 0) + 1

    # Sort findings: critical first, then by confidence desc
    all_findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.get("severity", "low"), 3), -f.get("confidence", 0)))

    now = datetime.now(timezone.utc).isoformat()
    output = {
        "scan_id": str(uuid.uuid4()),
        "timestamp": now,
        "total_findings": len(all_findings),
        "by_severity": by_severity,
        "by_category": by_category,
        "findings": all_findings,
        "warnings": warnings,
        "critic_validation": {
            "passed": False,
            "concerns": ["Critic Engine MUST be invoked separately (see skills/critic/SKILL.md)"],
            "plan_completeness": "partial",
            "mvp_disguised": None,
        },
    }

    output_path.write_text(json.dumps(output, indent=2))
    print(json.dumps({
        "output": str(output_path),
        "total_findings": len(all_findings),
        "by_severity": by_severity,
        "warnings": len(warnings),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
