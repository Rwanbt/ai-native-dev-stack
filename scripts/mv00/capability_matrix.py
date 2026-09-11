"""Build the fail-closed MV-00 capability matrix from executed probe reports."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

REPORTS = {"rest": "REST-FEASIBILITY-REPORT.json", "semantic": "SMART-CONNECTIONS-EGRESS-REPORT.json", "obsidian_git": "OBSIDIAN-GIT-BEHAVIOR-REPORT.json", "harness": "HARNESS-AUTOLOAD-REPORT.json", "git_transport": "GIT-TRANSPORT-REPORT.json", "model": "MODEL-EGRESS-REPORT.json"}

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--reports", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); args=parser.parse_args()
    evidence={name: json.loads((args.reports / file).read_text(encoding="utf-8")) for name,file in REPORTS.items()}
    result={"schema_version":1,"recorded_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"evidence":evidence,"qualified_tuples":[],"sensitive_admission":"DENY","reason":"no tuple has verified egress, containment, vault binding, and governed transfer"}
    args.output.write_text(json.dumps(result,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(result,sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
