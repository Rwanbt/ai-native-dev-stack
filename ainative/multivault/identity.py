"""Descriptive vault and checkout identities; trusted binding arrives in MV-04."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import subprocess

@dataclass(frozen=True)
class VaultIdentity:
    logical_id: str
    canonical_root: str

def discover_vault(logical_id: str, root: Path) -> VaultIdentity:
    if not logical_id:
        raise ValueError("logical vault identity is required")
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError("vault root is unavailable")
    return VaultIdentity(logical_id, str(resolved))

@dataclass(frozen=True)
class CheckoutIdentity:
    canonical_root: str
    common_git_dir: str
    origin_url: str | None

def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError("checkout identity is unavailable")
    return result.stdout.strip()

def discover_checkout(root: Path) -> CheckoutIdentity:
    resolved = root.resolve()
    common = _git(resolved, "rev-parse", "--path-format=absolute", "--git-common-dir")
    origin = subprocess.run(["git", "-C", str(resolved), "remote", "get-url", "origin"], capture_output=True, text=True, check=False)
    return CheckoutIdentity(str(resolved), common, origin.stdout.strip() or None)
