"""Product CLI E2E: exec and sync run through the composition roots from argv only."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative.multivault.__main__ import main as cli_main
from ainative.multivault.authority_store import AuthorityStore
from ainative.multivault.identity import (
    checkout_identity_digest,
    discover_checkout,
    discover_vault,
    vault_root_identity,
)


class CliExecSyncProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.base = base
        self.vault = base / "vault-a"
        self.vault.mkdir()
        self.other_vault = base / "vault-b"
        self.other_vault.mkdir()
        self.checkout = self.git_repository("checkout-a")
        self.workspace = base / "workspace"
        self.workspace.mkdir()
        self.store = AuthorityStore(base / "authority.json")
        self.binding = {
            "vault": "vault-a",
            "checkout": "checkout-a",
            "classification": "PERSONAL",
            "roots": [],
            "root_identity": vault_root_identity(discover_vault("vault-a", self.vault)),
            "checkout_identity": checkout_identity_digest(discover_checkout(self.checkout)),
        }
        self.store.replace({"company-a": dict(self.binding)})
        self.operator_state = base / "operator-state.json"
        self.operator_state.write_text(json.dumps({
            "classification": "PERSONAL",
            "project_security_id": "project-a",
            "approved_model_egress_digest": "egress",
            "memory_policy_digest": "memory",
            "persistence_assurance_digest": "persistence",
            "execution_profile": "profile",
            "runtime_observation_policy_digest": "observation",
            "security_epoch": {"epoch_counter_or_nonce": "1", "authority_instance_generation": "1"},
            "repository_roots": [str(self.workspace)],
            "vault_memory_roots": [str(self.vault)],
        }), encoding="utf-8")
        evidence = {
            field: f"v-{field}"
            for field in (
                "harness_binary_identity", "harness_version", "config_root_digest",
                "provider_principal", "effective_model_id", "routing_class",
                "endpoint_policy_digest", "plugin_inventory_digest", "adapter_version", "probe_version",
            )
        }
        evidence.update({
            "provider_ok": True, "model_ok": True, "endpoint_ok": True,
            "auth_store_ok": True, "containment_ok": True,
        })
        self.probe_evidence = base / "probe-evidence.json"
        self.probe_evidence.write_text(json.dumps(evidence), encoding="utf-8")
        self.origin = base / "origin.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.origin)], check=True)
        self.repo, self.url = self.repository_with_origin()
        self.git_state = base / "git-state.json"
        self.git_state.write_text(json.dumps({
            "approved_remote": {
                "canonical_fetch_url": self.url, "canonical_push_url": self.url,
                "provider_type": "local", "stable_repository_id": None,
                "required_owner_org": "local-team", "required_visibility_for_push": "private",
                "allowed_refs": ["refs/heads/*"], "require_stable_repository_id": False,
            },
            "transport_policy": {
                "protocol_allowlist": ["file"], "transport_executable_identity": "git-local",
                "proxy": None, "ssh_command": None, "credential_helper": None,
                "ssh_peer_policy": "pinned", "tls_peer_policy": "pinned",
                "effective_transport_config_digest": "digest-1",
            },
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def git_repository(self, name):
        root = Path(self.temp.name) / name
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
             "commit", "--allow-empty", "-q", "-m", "init"], check=True)
        return root

    def repository_with_origin(self):
        repo = Path(self.temp.name) / "repo"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
             "commit", "--allow-empty", "-q", "-m", "init"], check=True)
        url = self.origin.as_uri()
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True)
        subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:refs/heads/main"], check=True)
        return repo, url

    def observed_document(self, url=None, **transport_overrides):
        transport = {
            "protocol": "file", "transport_executable_identity": "git-local",
            "proxy": None, "ssh_command": None, "credential_helper": None,
            "effective_transport_config_digest": "digest-1",
        }
        transport.update(transport_overrides)
        return json.dumps({
            "remote": {
                "provider_type": "local", "stable_repository_id": None, "owner_org": "local-team",
                "visibility": "private",
                "effective_fetch_url": url or self.url,
                "effective_push_url": url or self.url,
            },
            "transport": transport,
        })

    def run_cli(self, arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli_main(arguments)
        return code, output.getvalue()

    def exec_arguments(self, marker, **overrides):
        command = [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('spawned')"]
        values = dict(
            store=self.store.path,
            domain="company-a",
            vault_root=self.vault,
            checkout_root=self.checkout,
            workspace=self.workspace,
            store_file=self.store.path,
        )
        values.update(overrides)
        return [
            "exec",
            "--store", str(values["store_file"]),
            "--domain", values["domain"],
            "--vault-id", "vault-a",
            "--checkout-id", "checkout-a",
            "--vault", str(values["vault_root"]),
            "--checkout", str(values["checkout_root"]),
            "--workspace", str(values["workspace"]),
            "--operator-state", str(self.operator_state),
            "--probe-evidence", str(self.probe_evidence),
            "--env", "APPROVED=1",
            "--os-env", "SystemRoot=C:/Windows",
            *command,
        ]

    def test_exec_nominal_spawns_once_through_the_composition_root(self):
        marker = self.base / "marker-nominal.txt"
        code, output = self.run_cli(self.exec_arguments(marker))
        self.assertEqual(0, code)
        self.assertIn("ALLOW_PHASE_B", output)
        self.assertTrue(marker.is_file())

    def test_exec_denial_never_spawns(self):
        marker = self.base / "marker-denied.txt"
        empty = self.base / "empty-authority.json"
        code, output = self.run_cli(self.exec_arguments(marker, store_file=empty))
        self.assertEqual(1, code)
        self.assertFalse(marker.exists())
        self.assertIn("DENY_DECLARATION_NOT_ADMITTED", output)

    def test_exec_stale_checkout_never_spawns(self):
        marker = self.base / "marker-stale.txt"
        code, output = self.run_cli(self.exec_arguments(marker, checkout_root=self.git_repository("checkout-other")))
        self.assertEqual(1, code)
        self.assertFalse(marker.exists())
        self.assertIn("DENY_CHECKOUT_STALE", output)

    def test_sync_approved_fetch_succeeds_through_the_engine(self):
        observed = self.base / "observed-ok.json"
        observed.write_text(self.observed_document(), encoding="utf-8")
        code, output = self.run_cli([
            "sync", "--store", str(self.store.path), "--domain", "company-a",
            "--vault-id", "vault-a", "--checkout-id", "checkout-a",
            "--vault", str(self.vault), "--checkout", str(self.checkout), "--repo", str(self.repo),
            "--git-state", str(self.git_state), "--observed", str(observed),
            "--refs", "refs/heads/main", "--verified-at", "2026-09-12T00:00:00Z",
        ])
        self.assertEqual(0, code)
        self.assertIn("ALLOW OK", output)

    def test_sync_mismatched_remote_is_denied_by_the_engine(self):
        observed = self.base / "observed-bad.json"
        observed.write_text(self.observed_document(url="file:///C:/elsewhere/repo"), encoding="utf-8")
        code, output = self.run_cli([
            "sync", "--store", str(self.store.path), "--domain", "company-a",
            "--vault-id", "vault-a", "--checkout-id", "checkout-a",
            "--vault", str(self.vault), "--checkout", str(self.checkout), "--repo", str(self.repo),
            "--git-state", str(self.git_state), "--observed", str(observed),
            "--refs", "refs/heads/main", "--verified-at", "2026-09-12T00:00:00Z",
        ])
        self.assertEqual(1, code)
        self.assertIn("DENY", output)


if __name__ == "__main__":
    unittest.main()
