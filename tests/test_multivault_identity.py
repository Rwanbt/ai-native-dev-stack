from pathlib import Path
import unittest
from ainative.multivault.identity import discover_checkout, discover_vault

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
