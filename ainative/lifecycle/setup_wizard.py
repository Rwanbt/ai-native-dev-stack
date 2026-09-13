"""`ainative setup` — the guided first run, composing the dedicated commands.

Every step asks before it mutates and is skippable; every mutation is the same
function the dedicated command runs (`ainative init`, `ainative machine init`,
the whole-stack doctor). Without a terminal the wizard refuses unless the
choices were given as flags, so scripts and CI keep using the dedicated
commands and no hidden step exists: what `setup` does is what the README
documents.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .errors import EXIT_FAILED, EXIT_OK, LifecycleError


def _ask(args, prompt: str) -> str | None:
    from ..cli import _ask as ask
    if getattr(args, "non_interactive", False) or getattr(args, "json", False):
        return None
    return ask(prompt)


def _yes(args, prompt: str) -> bool:
    answer = _ask(args, prompt)
    return (answer or "").lower() in ("y", "yes")


def _resolve_vault_pair(args) -> tuple[Path | None, str | None]:
    raw_vault = getattr(args, "vault", None) or os.environ.get("OBSIDIAN_VAULT")
    slug = getattr(args, "project_slug", None) or os.environ.get("OBSIDIAN_PROJECT_SLUG")
    vault = Path(raw_vault).expanduser() if raw_vault else None
    if (vault is None) != (slug is None):
        raise LifecycleError(
            "SETUP_VAULT_PAIR_REQUIRED",
            "a vault needs both halves: pass --vault and --project-slug "
            "together, or configure OBSIDIAN_VAULT and OBSIDIAN_PROJECT_SLUG")
    if vault is not None and not (vault / "AGENTS.md").is_file():
        raise LifecycleError("SETUP_VAULT_UNREADABLE",
                             f"{vault} does not look like a vault (no AGENTS.md)")
    return vault, slug


def run(args) -> int:
    project = (Path(args.project).expanduser() if getattr(args, "project", None)
               else Path.cwd())
    home = (Path(args.home).expanduser() if getattr(args, "home", None)
            else Path.home())
    # `--json` is a scripting surface too: it must never block on a prompt,
    # so it consents the same way `--non-interactive` does (through flags).
    non_interactive = bool(getattr(args, "non_interactive", False)
                           or getattr(args, "json", False))
    record: dict = {"operation": "setup", "project": str(project),
                    "home": str(home)}

    # 1. What is already here.
    from . import environment
    detected = [label for relative, label in environment.HARNESS_TARGETS
                if (home / relative).is_file()]
    record["harnesses"] = detected
    if not args.json:
        print(f"AI Native setup — project {project}")
        print(f"AI harnesses found in {home}: "
              + (", ".join(detected) if detected else "none yet (that is fine)"))

    # 2. Choose a profile, or explain why we cannot ask.
    profile = getattr(args, "profile", None)
    if profile is None:
        from ..cli import _choose_profile
        try:
            profile = _choose_profile(args)
        except LifecycleError:
            raise LifecycleError(
                "SETUP_CHOICES_REQUIRED",
                "no terminal to ask on and no choices given. Run "
                "`ainative setup --profile standard|verified [--machine]`, or "
                "`ainative init --profile ...` for automation.") from None
    record["profile"] = profile

    # 3. Project install (skippable; the flag is the consent when scripted).
    state_file = project / ".ai-native" / "lifecycle" / "state.json"
    if state_file.is_file() and not args.json:
        print(f"{project} already has an installation — this refreshes it "
              f"(`ainative profile status` shows the current one).")
    do_project = True if non_interactive else _yes(
        args, f"Install the {profile} profile into {project}? [y/N]: ")
    record["project_install"] = None
    if do_project:
        from . import installer
        result = installer.install(project, profile, dry_run=args.dry_run)
        record["project_install"] = {
            "profile": profile, "dry_run": result.dry_run,
            "changes": len(result.plan.changes),
        }
        if not args.json:
            from ..cli import _plan_text
            print(_plan_text(result))
    elif not args.json:
        print(f"skipped the project install (run `ainative init --profile {profile}`)")

    # 4. Machine-wide integration (skippable; --machine is the consent).
    vault, slug = _resolve_vault_pair(args)
    do_machine = (bool(getattr(args, "machine", False)) if non_interactive
                  else _yes(args, f"Install the shared method for every AI "
                                  f"harness in {home}? [y/N]: "))
    record["machine_install"] = None
    if do_machine:
        from . import machine as machinelib
        from . import machine_install
        from . import source as sourcelib
        stack = sourcelib.resolve().root
        try:
            report = machine_install.install(
                home, stack, vault=vault, slug=slug, dry_run=args.dry_run,
                printer=(lambda *_a, **_k: None) if args.json else print)
        except machinelib.MachineLifecycleError as refusal:
            raise LifecycleError(
                "MACHINE_MANIFEST_UNREADABLE",
                f"{refusal} — remove the manifest to start fresh") from refusal
        record["machine_install"] = {
            "changes": report.changes, "errors": report.errors,
            "assets": report.assets,
            "manifest": str(report.manifest) if report.manifest else None,
        }
    elif not args.json:
        print("skipped the machine-wide install (run `ainative machine init`)")

    # 5. Optional surroundings: detected and reported, never installed.
    graph = (os.environ.get("GRAPHIFY_BIN")
             or ("graphify-out/graph.json"
                 if (project / "graphify-out" / "graph.json").is_file() else None))
    record["optional"] = {"vault": str(vault) if vault else "not configured",
                          "graphify": graph or "not detected"}
    if not args.json:
        print(f"Optional: vault {record['optional']['vault']}; "
              f"graphify {record['optional']['graphify']}")

    # 6. Finish with the same doctor every other command runs.
    from ..cli import _doctor_collect, _emit
    diagnosis, _knowledge, _checks, healthy = _doctor_collect(
        project, check_updates=False)
    record["doctor"] = {"healthy": healthy, "installed": diagnosis.installed,
                        "profile": diagnosis.active_profile}
    if args.json:
        _emit(record)
    else:
        print("Doctor: " + ("healthy" if healthy
                            else "needs attention — run `ainative doctor`"))
        if healthy:
            print("Next: `ainative status`; `ainative update check`; "
                  "machine-wide `ainative machine status`.")
    return EXIT_OK if healthy else EXIT_FAILED


__all__ = ["run"]
