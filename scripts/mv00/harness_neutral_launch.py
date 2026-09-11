"""MV-00.4 — OpenCode neutral-launch autoload probe (versioned).

Creates a neutral project with a project agent and skill, then asks the
installed harness itself (`opencode debug ...`) what it would load. No model
calls, no network use. Other harnesses need their own adapter.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess


CONFIG = '{"$schema":"https://opencode.ai/config.json","agent":{"probe-agent":{"description":"neutral launch probe agent","mode":"subagent"}}}'
SKILL = "---\nname: probe-skill\ndescription: neutral launch probe skill\n---\n"


def _run(executable: str, *arguments: str, cwd: Path):
    try:
        return subprocess.run([executable, *arguments], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    except OSError:
        return None


def _executable() -> str | None:
    for candidate in ("opencode.cmd", "opencode.exe", "opencode"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def probe_opencode() -> dict:
    executable = _executable()
    if executable is None:
        return {
            "schema_version": 1,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "harness": "opencode",
            "harness_version": "UNKNOWN",
            "observation": "none",
            "disable_control": "UNKNOWN",
            "sensitive_available": False,
            "agent_autoload": "UNKNOWN",
            "skill_autoload": "UNKNOWN",
            "pure_flag_effect": "UNKNOWN",
            "reason": "opencode executable not found",
        }
    import tempfile

    with tempfile.TemporaryDirectory(prefix="mv00-opencode-") as directory:
        root = Path(directory)
        skill_dir = root / ".opencode" / "skills" / "probe-skill"
        skill_dir.mkdir(parents=True)
        (root / "opencode.json").write_text(CONFIG, encoding="utf-8")
        (skill_dir / "SKILL.md").write_text(SKILL, encoding="utf-8")
        version = _run(executable, "--version", cwd=root)
        agent = _run(executable, "debug", "agent", "probe-agent", cwd=root)
        agent_pure = _run(executable, "debug", "agent", "probe-agent", "--pure", cwd=root)
        skills = _run(executable, "debug", "skill", cwd=root)
    agent_loaded = agent is not None and agent.returncode == 0 and '"name": "probe-agent"' in agent.stdout
    agent_loaded_pure = agent_pure is not None and agent_pure.returncode == 0 and '"name": "probe-agent"' in agent_pure.stdout
    skill_loaded = skills is not None and skills.returncode == 0 and '"name": "probe-skill"' in skills.stdout
    if agent_loaded and skill_loaded:
        loaded = "VERIFIED"
    elif agent_loaded or skill_loaded:
        loaded = "PARTIAL"
    else:
        loaded = "NONE"
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "harness": "opencode",
        "harness_version": (version.stdout.strip() if version is not None and version.returncode == 0 else "UNKNOWN"),
        "observation": "per_operation",
        "disable_control": "UNKNOWN",
        "sensitive_available": False,
        "project_autoload": loaded,
        "agent_autoload": "VERIFIED" if agent_loaded else "NONE",
        "skill_autoload": "VERIFIED" if skill_loaded else "NONE",
        "pure_flag_effect": "project autoload persists" if (agent_loaded and agent_loaded_pure) else "changed",
        "reason": "project config and skills autoload; no proven disable control; debug commands observe effective config per operation",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = probe_opencode()
    encoded = json.dumps(report, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())