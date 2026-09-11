from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from ainative.multivault.identity import discover_checkout, discover_vault


def init_repository(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "--allow-empty", "-q", "-m", "init"],
        check=True,
    )


def create_junction(link: Path, target: Path) -> bool:
    if link.exists():
        link.rmdir()
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True, check=False)
    return result.returncode == 0


class MultiVaultIdentityTests(unittest.TestCase):
    def test_vault_requires_explicit_logical_identity(self):
        with self.assertRaises(ValueError): discover_vault("", Path.cwd())
    def test_vault_resolves_existing_root(self):
        identity=discover_vault("vault-a", Path.cwd())
        self.assertEqual("vault-a", identity.logical_id)
        self.assertTrue(Path(identity.canonical_root).is_absolute())
    def test_checkout_resolves_current_git_worktree(self):
        identity=discover_checkout(Path.cwd())
        self.assertTrue(Path(identity.canonical_root).is_absolute())
        self.assertTrue(Path(identity.common_git_dir).is_absolute())

    def test_vault_identity_captures_device_and_root_file_identity(self):
        identity = discover_vault("vault-a", Path.cwd())
        self.assertTrue(identity.device_identity)
        self.assertTrue(identity.root_file_identity)

    def test_copied_checkout_does_not_share_the_original_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            origin = Path(directory) / "origin"
            init_repository(origin)
            copy = Path(directory) / "copy"
            shutil.copytree(origin, copy)
            self.assertNotEqual(discover_checkout(origin), discover_checkout(copy))

    def test_linked_worktrees_share_common_git_dir_but_not_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            origin = Path(directory) / "origin"
            init_repository(origin)
            worktree = Path(directory) / "linked"
            subprocess.run(["git", "-C", str(origin), "worktree", "add", "-q", "-b", "linked", str(worktree)], check=True)
            primary = discover_checkout(origin)
            linked = discover_checkout(worktree)
            self.assertEqual(primary.common_git_dir, linked.common_git_dir)
            self.assertNotEqual(primary.git_dir, linked.git_dir)
            self.assertNotEqual(primary, linked)

    def test_symlinked_vault_root_is_detected_as_its_canonical_target(self):
        with tempfile.TemporaryDirectory() as directory:
            real = Path(directory) / "real-vault"
            real.mkdir()
            link = Path(directory) / "linked-vault"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks are unavailable on this platform")
            self.assertEqual(discover_vault("v", real).canonical_root, discover_vault("v", link).canonical_root)

    def test_junction_swap_changes_the_discovered_identity(self):
        if not sys.platform.startswith("win"):
            self.skipTest("junction swap test targets Windows")
        with tempfile.TemporaryDirectory() as directory:
            first_target = Path(directory) / "first"
            second_target = Path(directory) / "second"
            first_target.mkdir()
            second_target.mkdir()
            link = Path(directory) / "vault-link"
            self.assertTrue(create_junction(link, first_target))
            before = discover_vault("v", link)
            self.assertTrue(create_junction(link, second_target))
            after = discover_vault("v", link)
            self.assertNotEqual(before.canonical_root, after.canonical_root)