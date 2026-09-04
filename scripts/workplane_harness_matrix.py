"""Run the same five-item pilot through two independent local harnesses."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ainative_workplane.controller import WorkController


def direct_harness(root: Path) -> int:
    for index in range(5):
        WorkController(root / f"direct-{index}").create({"task": {"index": index}})
    return 5


def cli_harness(root: Path) -> int:
    for index in range(5):
        work = root / f"cli-{index}"
        subprocess.check_call([sys.executable, "-m", "ainative_workplane", "work", "new", str(work), "--artifact", f"task={{\"index\":{index}}}"])
    return 5


def run() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="workplane-harness-") as directory:
        root = Path(directory)
        return {"direct_api": direct_harness(root), "cli_facade": cli_harness(root), "external_harness": False}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
