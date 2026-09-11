import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.cli import main as product_main
from ainative.multivault.__main__ import main as multivault_main


def git_repository(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
         "commit", "--allow-empty", "-q", "-m", "init"], check=True)
    return root


class MultiVaultCliTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.base = Path(self._temporary.name)
        self.store = self.base / "authority.json"
        self.vault = self.base / "vault-personal"
        self.vault.mkdir()
        self.checkout = git_repository(self.base / "checkout-personal")

    def tearDown(self):
        self._temporary.cleanup()

    def bind(self, *extra):
        return multivault_main([
            "bind", "--store", str(self.store), "--domain", "personal",
            "--vault-id", "vault-personal", "--checkout-id", "checkout-personal",
            "--vault", str(self.vault), "--checkout", str(self.checkout), *extra,
        ])

    def test_bind_records_operator_intent_with_real_measurements(self):
        self.assertEqual(0, self.bind())
        from ainative.multivault.authority_store import AuthorityStore
        from ainative.multivault.binding import WorkspaceDeclaration, admit
        binding = AuthorityStore(self.store).binding("personal")
        self.assertEqual("vault-personal", binding["vault"])
        self.assertEqual("checkout-personal", binding["checkout"])
        self.assertTrue(binding["root_identity"])
        from ainative.multivault.identity import checkout_identity_digest, discover_checkout
        self.assertEqual(
            checkout_identity_digest(discover_checkout(self.checkout)),
            binding["checkout_identity"],
        )
        self.assertTrue(admit(WorkspaceDeclaration("personal", "vault-personal", "checkout-personal"),
                              AuthorityStore(self.store)))

    def test_bind_refuses_a_missing_vault_root(self):
        code = multivault_main([
            "bind", "--store", str(self.store), "--domain", "personal",
            "--vault-id", "vault-personal", "--checkout-id", "checkout-personal",
            "--vault", str(self.base / "missing"), "--checkout", str(self.checkout),
        ])
        self.assertEqual(1, code)
        self.assertFalse(self.store.exists())

    def test_bind_refuses_a_corrupt_authority_store(self):
        self.store.write_text("{not json", encoding="utf-8")
        self.assertEqual(1, self.bind())

    def test_context_without_binding_is_missing(self):
        code = multivault_main(["context", "--store", str(self.store), "--domain", "personal"])
        self.assertEqual(1, code)

    def test_doctor_without_binding_is_not_green(self):
        code = multivault_main(["doctor", "--store", str(self.store), "--domain", "personal",
                                "--repo", str(self.checkout)])
        self.assertEqual(1, code)

    def test_product_cli_routes_the_multivault_namespace(self):
        with self.assertRaises(SystemExit) as raised:
            product_main(["multivault", "--help"])
        self.assertEqual(0, raised.exception.code)
        code = product_main(["multivault", "context", "--store", str(self.store), "--domain", "personal"])
        self.assertEqual(1, code)

    def test_doctor_reports_the_measured_checkout_identity_after_bind(self):
        import contextlib
        import io
        self.assertEqual(0, self.bind())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            multivault_main(["doctor", "--store", str(self.store), "--domain", "personal",
                             "--repo", str(self.checkout)])
        self.assertIn("PASS\tcheckout_identity", output.getvalue())

    def test_explicit_rebind_migrates_a_legacy_binding(self):
        from ainative.multivault.authority_store import AuthorityStore
        AuthorityStore(self.store).replace({"personal": {
            "vault": "vault-personal", "checkout": "checkout-personal",
            "classification": "PERSONAL", "roots": [],
        }})
        self.assertEqual(0, self.bind())
        self.assertTrue(AuthorityStore(self.store).binding("personal")["checkout_identity"])

    def test_multivault_cli_does_not_reimplement_security_policies(self):
        source = Path("ainative/multivault/__main__.py").read_text(encoding="utf-8")
        for forbidden in ("AllowedContextEnvelope(", "RuntimeContextHandle(", "SensitiveQualification(",
                          "GovernedPushCapability(", "classification >=", "CONFIDENTIAL", "CRITICAL"):
            self.assertNotIn(forbidden, source)