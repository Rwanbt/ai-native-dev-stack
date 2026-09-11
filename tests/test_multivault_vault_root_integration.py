import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative.multivault.__main__ import main as cli_main

from ainative.multivault.authority_store import AuthorityStore
from ainative.multivault.binding import (
    ALLOW_ROOT_FRESH,
    DENY_ROOT_IDENTITY_UNRECORDED,
    DENY_ROOT_MEASUREMENT_INCOMPLETE,
    DENY_ROOT_STALE,
    WorkspaceDeclaration,
)
from ainative.multivault.identity import discover_vault, vault_root_identity
from ainative.multivault.resolver import resolve_with_vault_root


def create_junction(link: Path, target: Path) -> bool:
    if link.exists():
        link.rmdir()
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True, check=False)
    return result.returncode == 0


class VaultRootIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.vault = base / "vault-a"
        self.other = base / "vault-b"
        self.vault.mkdir()
        self.other.mkdir()
        self.store = AuthorityStore(base / "authority.json")
        self.checkout = self.git_repository("checkout-default")
        self.recorded = vault_root_identity(discover_vault("vault-a", self.vault))
        self.write_binding(root_identity=self.recorded)
        self.declaration = WorkspaceDeclaration("company-a", "vault-a", "checkout-a")

    def tearDown(self):
        self.temp.cleanup()

    def write_binding(self, root_identity=None, checkout_identity="__fixture__"):
        from ainative.multivault.identity import checkout_identity_digest, discover_checkout
        binding = {"vault": "vault-a", "checkout": "checkout-a", "classification": "PERSONAL", "roots": []}
        if root_identity is not None:
            binding["root_identity"] = root_identity
        if checkout_identity == "__fixture__":
            checkout_identity = checkout_identity_digest(discover_checkout(self.checkout))
        if checkout_identity is not None:
            binding["checkout_identity"] = checkout_identity
        self.store.replace({"company-a": binding})

    def git_repository(self, name):
        import subprocess
        root = Path(self.temp.name) / name
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
             "commit", "--allow-empty", "-q", "-m", "init"], check=True)
        return root

    def resolve(self, root):
        return resolve_with_vault_root(self.declaration, self.store, root, checkout_root=self.checkout)

    def test_correct_root_is_authorized_and_fresh(self):
        result = self.resolve(self.vault)
        self.assertTrue(result.authorized)
        self.assertEqual(ALLOW_ROOT_FRESH, result.root_freshness.decision)

    def test_wrong_vault_denies(self):
        result = self.resolve(self.other)
        self.assertFalse(result.authorized)
        self.assertEqual(DENY_ROOT_STALE, result.root_freshness.decision)

    def test_binding_copied_to_foreign_vault_denies(self):
        result = resolve_with_vault_root(
            WorkspaceDeclaration("company-a", "vault-a", "checkout-a"), self.store, self.other
        )
        self.assertFalse(result.authorized)
        self.assertEqual(DENY_ROOT_STALE, result.root_freshness.decision)

    def test_binding_without_root_identity_denies(self):
        self.write_binding(root_identity=None)
        result = self.resolve(self.vault)
        self.assertFalse(result.authorized)
        self.assertEqual(DENY_ROOT_IDENTITY_UNRECORDED, result.root_freshness.decision)

    def test_measurement_failure_denies(self):
        missing = Path(self.temp.name) / "missing-vault"
        result = self.resolve(missing)
        self.assertFalse(result.authorized)
        self.assertEqual(DENY_ROOT_MEASUREMENT_INCOMPLETE, result.root_freshness.decision)

    def test_junction_swap_denies(self):
        if not sys.platform.startswith("win"):
            self.skipTest("junction swap test targets Windows")
        link = Path(self.temp.name) / "vault-link"
        if not create_junction(link, self.vault):
            self.skipTest("junctions are unavailable on this platform")
        self.assertTrue(self.resolve(link).authorized)
        self.assertTrue(create_junction(link, self.other))
        result = self.resolve(link)
        self.assertFalse(result.authorized)
        self.assertEqual(DENY_ROOT_STALE, result.root_freshness.decision)

    def test_replaced_root_denies(self):
        if not sys.platform.startswith("win"):
            self.skipTest("junction replacement test targets Windows")
        self.vault.rmdir()
        if not create_junction(self.vault, self.other):
            self.skipTest("junctions are unavailable on this platform")
        result = self.resolve(self.vault)
        self.assertFalse(result.authorized)
        self.assertEqual(DENY_ROOT_STALE, result.root_freshness.decision)

    def run_doctor(self, *extra):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli_main(["doctor", "--store", str(self.store.path), "--domain", "company-a", *extra])
        return code, output.getvalue()

    def test_doctor_reports_passing_root_freshness(self):
        code, output = self.run_doctor("--vault-root", str(self.vault))
        self.assertIn("PASS\troot_freshness", output)

    def test_doctor_reports_stale_root(self):
        code, output = self.run_doctor("--vault-root", str(self.other))
        self.assertIn("FAIL\troot_freshness", output)

    def test_doctor_without_root_is_not_a_pass(self):
        code, output = self.run_doctor()
        self.assertIn("UNKNOWN\troot_freshness", output)

    def test_doctor_reports_unrecorded_root_identity(self):
        self.write_binding(root_identity=None)
        code, output = self.run_doctor("--vault-root", str(self.vault))
        self.assertIn("FAIL\troot_freshness", output)

    def test_matching_checkout_identity_authorizes(self):
        from ainative.multivault.identity import checkout_identity_digest, discover_checkout
        checkout = self.git_repository("checkout-a")
        self.write_binding(root_identity=self.recorded, checkout_identity=checkout_identity_digest(discover_checkout(checkout)))
        result = resolve_with_vault_root(self.declaration, self.store, self.vault, checkout_root=checkout)
        self.assertTrue(result.authorized)
        self.assertEqual("ALLOW_CHECKOUT_FRESH", result.checkout_freshness.decision)

    def test_copied_or_moved_checkout_denies(self):
        from ainative.multivault.identity import checkout_identity_digest, discover_checkout
        checkout_a = self.git_repository("checkout-a")
        checkout_b = self.git_repository("checkout-b")
        self.write_binding(root_identity=self.recorded, checkout_identity=checkout_identity_digest(discover_checkout(checkout_a)))
        result = resolve_with_vault_root(self.declaration, self.store, self.vault, checkout_root=checkout_b)
        self.assertFalse(result.authorized)
        self.assertEqual("DENY_CHECKOUT_STALE", result.checkout_freshness.decision)

    def test_recorded_checkout_identity_requires_a_live_measurement(self):
        from ainative.multivault.identity import checkout_identity_digest, discover_checkout
        checkout = self.git_repository("checkout-a")
        self.write_binding(root_identity=self.recorded, checkout_identity=checkout_identity_digest(discover_checkout(checkout)))
        result = resolve_with_vault_root(self.declaration, self.store, self.vault)
        self.assertFalse(result.authorized)
        self.assertEqual("DENY_CHECKOUT_MEASUREMENT_INCOMPLETE", result.checkout_freshness.decision)

    def test_legacy_binding_without_checkout_identity_denies(self):
        self.write_binding(root_identity=self.recorded, checkout_identity=None)
        result = self.resolve(self.vault)
        self.assertFalse(result.authorized)
        self.assertEqual("DENY_CHECKOUT_IDENTITY_UNRECORDED", result.checkout_freshness.decision)

    def test_legacy_confidential_binding_denies_before_any_gate(self):
        self.store.replace({"company-a": {
            "vault": "vault-a", "checkout": "checkout-a", "classification": "CONFIDENTIAL",
            "roots": [], "root_identity": self.recorded,
        }})
        result = self.resolve(self.vault)
        self.assertFalse(result.authorized)
        self.assertEqual("DENY_CHECKOUT_IDENTITY_UNRECORDED", result.checkout_freshness.decision)

    def test_stale_after_identity_change_denies(self):
        self.write_binding(root_identity="sha256:changed")
        result = self.resolve(self.vault)
        self.assertFalse(result.authorized)
        self.assertEqual(DENY_ROOT_STALE, result.root_freshness.decision)