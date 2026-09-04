"""Shared fixtures for the lifecycle suite.

Every test builds a throwaway project and a throwaway *distribution*, so the
suite never installs from — or into — the developer's checkout, and a change to
the real `skills/` tree cannot make a lifecycle assertion pass or fail for the
wrong reason.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ainative.lifecycle import manifest as manifestlib   # noqa: E402
from ainative.lifecycle import source as sourcelib       # noqa: E402


def build_distribution_tree(root: Path, version: str = "1.0.0", *,
                            extra_skill: str | None = None) -> Path:
    """A minimal but complete stack source: the markers plus real content."""

    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(f"# Engineering method {version}\n", encoding="utf-8")
    (root / "conventions.json").write_text(
        json.dumps({"schema": 1, "version": version}) + "\n", encoding="utf-8")

    tools = root / "tools" / "ai_docs"
    tools.mkdir(parents=True, exist_ok=True)
    for name in ("source_config.py", "module_discovery.py", "generate_ai_summary.py",
                 "update_on_edit.py", "generate_all.py", "generate_metrics.py",
                 "assemble_context.py"):
        (tools / name).write_text(f"# {name} {version}\n", encoding="utf-8")
    (tools / "run_hook.sh").write_text(f"#!/bin/sh\n# {version}\n", encoding="utf-8")
    (tools / "find_python.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (tools / "config.sh.example").write_text(f"VAULT=\n# {version}\n", encoding="utf-8")

    templates = root / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    (templates / "AI_CONTEXT_template.md").write_text(f"# context {version}\n", encoding="utf-8")

    skills = root / "skills"
    for name in ["demo-skill"] + ([extra_skill] if extra_skill else []):
        target = skills / name
        target.mkdir(parents=True, exist_ok=True)
        (target / "SKILL.md").write_text(f"# {name} {version}\n", encoding="utf-8")

    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "VERIFIED-WORK-PLANE.md").write_text(f"# work plane {version}\n", encoding="utf-8")
    return root


def make_release_archive(distribution: Path, destination: Path) -> Path:
    """Zip a distribution the way a release publishes it: one top-level dir."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(distribution.rglob("*")):
            if item.is_file():
                archive.write(item, f"stack/{item.relative_to(distribution).as_posix()}")
    return destination


class LifecycleTestCase(unittest.TestCase):
    """A throwaway project, a throwaway distribution, and no ambient state."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ainative-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.project = self.root / "project"
        (self.project / "src").mkdir(parents=True)
        (self.project / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
        (self.project / "README.md").write_text("my project\n", encoding="utf-8")
        self.distribution_root = build_distribution_tree(self.root / "dist-v1", "1.0.0")
        self.distribution = manifestlib.load()
        self.source = sourcelib.DistributionSource(
            root=self.distribution_root.resolve(), origin="test", version="1.0.0")
        # No inherited update configuration may reach a test.
        for name in ("AINATIVE_UPDATE_PROVIDER", "AINATIVE_UPDATE_LOCAL_DIR",
                     "AINATIVE_UPDATE_URL", "AINATIVE_NO_UPDATE_CHECK",
                     "AINATIVE_STACK_SOURCE"):
            self._unset(name)

    def _unset(self, name: str) -> None:
        previous = os.environ.pop(name, None)
        if previous is not None:
            self.addCleanup(os.environ.__setitem__, name, previous)

    def set_env(self, name: str, value: str) -> None:
        previous = os.environ.get(name)
        os.environ[name] = value
        if previous is None:
            self.addCleanup(os.environ.pop, name, None)
        else:
            self.addCleanup(os.environ.__setitem__, name, previous)

    # --- helpers ---------------------------------------------------------

    def install(self, profile: str = "standard", **kwargs):
        from ainative.lifecycle import installer

        return installer.install(self.project, profile, distribution=self.distribution,
                                 source=self.source, **kwargs)

    def switch(self, profile: str, **kwargs):
        from ainative.lifecycle import installer

        return installer.install(self.project, profile, operation="profile-switch",
                                 distribution=self.distribution, source=self.source, **kwargs)

    def uninstall(self, **kwargs):
        from ainative.lifecycle import uninstaller

        return uninstaller.uninstall(self.project, distribution=self.distribution, **kwargs)

    def state(self):
        from ainative.lifecycle import state as statelib

        return statelib.load(self.project)

    def read(self, relative: str) -> str:
        return (self.project / relative).read_text(encoding="utf-8")

    def write(self, relative: str, content: str) -> Path:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def exists(self, relative: str) -> bool:
        return (self.project / relative).exists()

    def seed_verified_history(self) -> dict[str, str]:
        """Representative Verified state: a trust anchor, a work, a run record."""

        payloads = {
            ".ai-native/trust/project_trust.json": '{"uid":"trust_1","trust_digest":"abc"}',
            ".ai-native/work/w1/manifest.json": '{"revision":3,"uid":"work_1"}',
            ".ai-native/work/w1/revisions/3.json": '{"revision":3}',
            ".ai-native/runs/run_1.json": '{"uid":"run_1","result":"PASS"}',
        }
        for relative, content in payloads.items():
            self.write(relative, content)
        return payloads

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        """Run the real console entry point in a child process."""

        environment = {**os.environ, "PYTHONIOENCODING": "utf-8",
                       "PYTHONPATH": str(REPO),
                       "AINATIVE_STACK_SOURCE": str(self.distribution_root)}
        # DEVNULL, not the parent's stdin: a suite whose behaviour depends on
        # whether the developer ran it from a terminal is not a suite.
        return subprocess.run([sys.executable, "-m", "ainative.cli", *args,
                               "--project", str(self.project)],
                              capture_output=True, text=True, env=environment,
                              stdin=subprocess.DEVNULL, cwd=str(REPO))

    def cli_bare(self, *args: str) -> subprocess.CompletedProcess:
        """The same, for commands that take no `--project`."""

        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(REPO),
                       "AINATIVE_STACK_SOURCE": str(self.distribution_root)}
        return subprocess.run([sys.executable, "-m", "ainative.cli", *args],
                              capture_output=True, text=True, env=environment,
                              stdin=subprocess.DEVNULL, cwd=str(REPO))


__all__ = ["LifecycleTestCase", "build_distribution_tree", "make_release_archive", "REPO"]
