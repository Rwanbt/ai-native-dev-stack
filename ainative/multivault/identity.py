"""Descriptive vault and checkout identities; trusted binding arrives in MV-04.

Device/volume and root file identity are captured so a mid-session mount or
junction retarget is detectable, per ADR-0015 section 5.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import subprocess

from .schema import digest as canonical_digest


@dataclass(frozen=True)
class VaultIdentity:
    logical_id: str
    canonical_root: str
    device_identity: str
    root_file_identity: str


def _device_identity(root: Path) -> tuple[str, str]:
    stat = root.stat()
    return str(stat.st_dev), str(stat.st_ino)


def discover_vault(logical_id: str, root: Path) -> VaultIdentity:
    if not logical_id:
        raise ValueError("logical vault identity is required")
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError("vault root is unavailable")
    device_identity, root_file_identity = _device_identity(resolved)
    return VaultIdentity(logical_id, str(resolved), device_identity, root_file_identity)


@dataclass(frozen=True)
class CheckoutIdentity:
    canonical_root: str
    git_dir: str
    common_git_dir: str
    origin_url: str | None


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError("checkout identity is unavailable")
    return result.stdout.strip()


def discover_checkout(root: Path) -> CheckoutIdentity:
    resolved = root.resolve()
    git_dir = _git(resolved, "rev-parse", "--path-format=absolute", "--git-dir")
    common = _git(resolved, "rev-parse", "--path-format=absolute", "--git-common-dir")
    origin = subprocess.run(["git", "-C", str(resolved), "remote", "get-url", "origin"], capture_output=True, text=True, check=False)
    return CheckoutIdentity(str(resolved), git_dir, common, origin.stdout.strip() or None)

def vault_root_identity(identity: VaultIdentity) -> str:
    """Digest of the ADR-0015 root identity primitives for binding comparison."""
    return canonical_digest({
        "canonical_root": identity.canonical_root,
        "device_identity": identity.device_identity,
        "root_file_identity": identity.root_file_identity,
    })


def measure_root_identity(logical_id: str, root: Path) -> str | None:
    """Best-effort root identity; absent or unreadable roots measure as None."""
    try:
        return vault_root_identity(discover_vault(logical_id, root))
    except (ValueError, OSError):
        return None


def checkout_identity_digest(identity: CheckoutIdentity) -> str:
    """Digest of the canonical checkout primitives for binding comparison."""
    return canonical_digest({
        "canonical_root": identity.canonical_root,
        "git_dir": identity.git_dir,
        "common_git_dir": identity.common_git_dir,
        "origin_url": identity.origin_url,
    })


def measure_checkout_identity(root: Path) -> str | None:
    """Best-effort checkout identity; absent or unreadable checkouts measure as None."""
    try:
        return checkout_identity_digest(discover_checkout(root))
    except (ValueError, OSError):
        return None
