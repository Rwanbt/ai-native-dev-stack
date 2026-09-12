"""Exec composition E2E: every denial returns before the launcher, nominal releases exactly once."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.multivault.authority_store import AuthorityStore
from ainative.multivault.exec_composition import (
    ExecRequest,
    compose_exec,
)
from ainative.multivault.harness_claude import (
    QUALIFICATION_FLAGS,
    measurement_from_probe_evidence,
)
from ainative.multivault.identity import (
    checkout_identity_digest,
    discover_checkout,
    discover_vault,
    vault_root_identity,
)
from ainative.multivault.runtime_authority import authority_from_operator_state
from ainative.multivault.schema import (
    SecurityEpoch,
    allowed_context_envelope_from_authoritative_roots,
)
from ainative.multivault.sensitive_launch import (
    ALLOW_PHASE_B,
    CARRIED_STATE_FIELDS,
    DENY_CARRIED_STATE_DRIFT,
    DENY_OBSERVATION_INCOMPLETE,
    DENY_PROJECT_INSTRUCTIONS,
    DENY_RUNTIME_AUTHORITY_LOST,
)


class RecordingSpawn:
    def __init__(self, failure=None):
        self.calls = 0
        self.kwargs = {}
        self.failure = failure

    def __call__(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        if self.failure is not None:
            raise self.failure
        return 0


class ExecCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.vault = base / "vault-a"
        self.vault.mkdir()
        self.other_vault = base / "vault-b"
        self.other_vault.mkdir()
        self.checkout = self.git_repository("checkout-a")
        self.copied_checkout = self.git_repository("checkout-copy")
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

    def request(self, **overrides):
        values = dict(
            store_path=self.store.path,
            domain="company-a",
            vault_logical_id="vault-a",
            checkout_identity="checkout-a",
            vault_root=self.vault,
            checkout_root=self.checkout,
            workspace=self.workspace,
            argv=("claude", "--version"),
            approved_env={"APPROVED": "1"},
            required_os_env={"SystemRoot": "C:/Windows"},
        )
        values.update(overrides)
        return ExecRequest(**values)

    def envelope(self):
        return allowed_context_envelope_from_authoritative_roots((str(self.workspace),), (str(self.vault),))

    def authority(self):
        return authority_from_operator_state(
            security_domain_id="company-a",
            vault_identity="vault-a",
            checkout_identity="checkout-a",
            project_security_id="project-a",
            classification="PERSONAL",
            allowed_context_envelope=self.envelope(),
            security_epoch=SecurityEpoch("company-a", "1", "1"),
            approved_model_egress_digest="egress",
            memory_policy_digest="memory",
            persistence_assurance_digest="persistence",
            execution_profile="profile",
            runtime_observation_policy_digest="observation",
        )

    def evidence(self, **overrides):
        values = {field: f"v-{field}" for field in CARRIED_STATE_FIELDS}
        values.update({flag: True for flag in QUALIFICATION_FLAGS})
        values.update(overrides)
        return values

    def measure_ok(self):
        captured = self.evidence()
        return lambda: measurement_from_probe_evidence(captured)

    def compose(self, spawn, **overrides):
        return compose_exec(
            self.request(**overrides),
            authority=self.authority(),
            envelope=self.envelope(),
            measure=self.measure_ok(),
            spawn=spawn,
        )

    def assert_denied(self, outcome, code):
        self.assertFalse(outcome.spawned)
        self.assertEqual(code, outcome.decision)
        self.assertIsNone(outcome.runtime_context_handle)
        self.assertIsNone(outcome.allowed_context_envelope)

    def test_wrong_domain_is_denied_without_spawn(self):
        spawn = RecordingSpawn()
        outcome = self.compose(spawn, domain="company-b")
        self.assert_denied(outcome, "DENY_DECLARATION_NOT_ADMITTED")
        self.assertEqual(0, spawn.calls)

    def test_missing_binding_is_denied_without_spawn(self):
        spawn = RecordingSpawn()
        empty = Path(self.temp.name) / "empty-authority.json"
        outcome = self.compose(spawn, store_path=empty)
        self.assert_denied(outcome, "DENY_DECLARATION_NOT_ADMITTED")
        self.assertEqual(0, spawn.calls)

    def test_stale_vault_is_denied_without_spawn(self):
        spawn = RecordingSpawn()
        outcome = self.compose(spawn, vault_root=self.other_vault)
        self.assert_denied(outcome, "DENY_ROOT_STALE")
        self.assertEqual(0, spawn.calls)

    def test_stale_copied_checkout_is_denied_without_spawn(self):
        spawn = RecordingSpawn()
        outcome = self.compose(spawn, checkout_root=self.copied_checkout)
        self.assert_denied(outcome, "DENY_CHECKOUT_STALE")
        self.assertEqual(0, spawn.calls)

    def test_legacy_binding_without_checkout_identity_is_denied(self):
        legacy = {key: value for key, value in self.binding.items() if key != "checkout_identity"}
        self.store.replace({"company-a": legacy})
        spawn = RecordingSpawn()
        outcome = self.compose(spawn)
        self.assert_denied(outcome, "DENY_CHECKOUT_IDENTITY_UNRECORDED")
        self.assertEqual(0, spawn.calls)

    def test_project_instruction_surface_denies_before_spawn(self):
        (self.workspace / "CLAUDE.md").write_text("instructions", encoding="utf-8")
        spawn = RecordingSpawn()
        outcome = self.compose(spawn)
        self.assert_denied(outcome, DENY_PROJECT_INSTRUCTIONS)
        self.assertEqual(0, spawn.calls)

    def test_repository_admission_denial_blocks_sensitive_classification(self):
        self.binding["classification"] = "TEAM"
        self.store.replace({"company-a": self.binding})
        spawn = RecordingSpawn()
        outcome = self.compose(spawn)
        self.assert_denied(outcome, "DENY_REPOSITORY_ADMISSION")
        self.assertEqual(0, spawn.calls)

    def test_incomplete_phase_a_measurement_denies_without_spawn(self):
        captured = self.evidence()
        del captured["harness_version"]
        spawn = RecordingSpawn()
        outcome = compose_exec(
            self.request(), authority=self.authority(), envelope=self.envelope(),
            measure=lambda: measurement_from_probe_evidence(captured), spawn=spawn,
        )
        self.assert_denied(outcome, DENY_OBSERVATION_INCOMPLETE)
        self.assertEqual(0, spawn.calls)

    def test_carried_state_drift_between_phases_denies_without_spawn(self):
        first = self.evidence()
        drifted = dict(first)
        drifted["harness_version"] = "drifted"
        calls = {"count": 0}

        def drifting():
            calls["count"] += 1
            return measurement_from_probe_evidence(first if calls["count"] == 1 else drifted)

        spawn = RecordingSpawn()
        outcome = compose_exec(
            self.request(), authority=self.authority(), envelope=self.envelope(),
            measure=drifting, spawn=spawn,
        )
        self.assert_denied(outcome, DENY_CARRIED_STATE_DRIFT)
        self.assertEqual(2, calls["count"])
        self.assertEqual(0, spawn.calls)

    def test_authority_loss_denies_without_spawn(self):
        spawn = RecordingSpawn()
        outcome = compose_exec(
            self.request(), authority=self.authority(), envelope=self.envelope(),
            measure=self.measure_ok(), spawn=spawn, authority_alive=lambda: False,
        )
        self.assert_denied(outcome, DENY_RUNTIME_AUTHORITY_LOST)
        self.assertEqual(0, spawn.calls)

    def test_launcher_loss_denies_without_spawn(self):
        spawn = RecordingSpawn()
        outcome = compose_exec(
            self.request(), authority=self.authority(), envelope=self.envelope(),
            measure=self.measure_ok(), spawn=spawn, launcher_alive=lambda: False,
        )
        self.assert_denied(outcome, DENY_RUNTIME_AUTHORITY_LOST)
        self.assertEqual(0, spawn.calls)

    def test_nominal_exec_releases_exact_objects_once(self):
        spawn = RecordingSpawn()
        outcome = self.compose(spawn)
        self.assertTrue(outcome.spawned)
        self.assertEqual(ALLOW_PHASE_B, outcome.decision)
        self.assertEqual(1, spawn.calls)
        self.assertIs(spawn.kwargs["runtime_context_handle"], outcome.runtime_context_handle)
        self.assertIs(spawn.kwargs["allowed_context_envelope"], outcome.allowed_context_envelope)
        self.assertEqual(["claude", "--version"], spawn.kwargs["argv"])
        self.assertEqual({"SystemRoot": "C:/Windows", "APPROVED": "1"}, dict(spawn.kwargs["env"]))
        self.assertNotIn("PATH", spawn.kwargs["env"])

    def test_launcher_failure_attempts_once_without_retry(self):
        spawn = RecordingSpawn(failure=RuntimeError("launcher exploded"))
        with self.assertRaises(RuntimeError):
            self.compose(spawn)
        self.assertEqual(1, spawn.calls)


class ExecCompositionStructureTests(unittest.TestCase):
    def test_composition_module_constructs_no_authoritative_object_or_decision(self):
        source = (Path(__file__).resolve().parent.parent / "ainative" / "multivault" / "exec_composition.py").read_text(encoding="utf-8")
        forbidden = (
            "AllowedContextEnvelope(",
            "RuntimeContextHandle(",
            "SensitiveQualification(",
            "GovernedPushCapability(",
            "SecurityClassification.CONFIDENTIAL",
            "SecurityClassification.CRITICAL",
            "classification >=",
            "classification >",
        )
        for token in forbidden:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
