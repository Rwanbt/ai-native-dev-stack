import tempfile
import unittest
from pathlib import Path

from ainative.multivault.runtime_authority import ImmutableAuthoritativeSecurityState, RuntimeAuthority
from ainative.multivault.schema import AllowedContextEnvelope, SecurityEpoch
from ainative.multivault.sensitive_launch import (
    ALLOW_PHASE_B,
    CARRIED_STATE_FIELDS,
    DENY_AUTH_STORE,
    DENY_CARRIED_STATE_DRIFT,
    DENY_CONTAINMENT,
    DENY_ENDPOINT_ROUTING,
    DENY_MODEL_IDENTITY,
    DENY_OBSERVATION_INCOMPLETE,
    DENY_PROJECT_INSTRUCTIONS,
    DENY_PROVIDER_IDENTITY,
    DENY_RUNTIME_AUTHORITY_LOST,
    SensitiveLaunchGate,
)


def make_authority():
    state = ImmutableAuthoritativeSecurityState(
        security_domain_id="company-a",
        security_epoch=SecurityEpoch("company-a", "1", "auth-1"),
        vault_identity="vault",
        checkout_identity="checkout",
        project_security_id="project",
        classification="CONFIDENTIAL",
        allowed_context_envelope=AllowedContextEnvelope(("/srv",), ("/srv",)),
        approved_model_egress_digest="egress",
        memory_policy_digest="m",
        persistence_assurance_digest="p",
        execution_profile="GUARDED",
        runtime_observation_policy_digest="o",
        authority_instance_id="auth-1",
    )
    return RuntimeAuthority(state)


def measure_ok(**overrides):
    data = {field: f"value-{field}" for field in CARRIED_STATE_FIELDS}
    data.update({"provider_ok": "true", "model_ok": "true", "endpoint_ok": "true", "auth_store_ok": "true", "containment_ok": "true"})
    data.update(overrides)
    return data


def build(measure, workspace, **hooks):
    authority = make_authority()
    envelope = AllowedContextEnvelope(("/srv",), ("/srv",))
    gate = SensitiveLaunchGate(
        workspace=workspace,
        security_domain_id="company-a",
        checkout_identity="checkout",
        authority=authority,
        envelope=envelope,
        measure=measure,
        **hooks,
    )
    return gate, authority, envelope


class SensitiveLaunchGateTests(unittest.TestCase):
    def clean_workspace(self, base):
        ws = Path(base) / "ws"
        ws.mkdir()
        return ws

    def test_phase_a_to_phase_b_nominal_releases_handle_and_envelope(self):
        with tempfile.TemporaryDirectory() as base:
            gate, authority, envelope = build(lambda: measure_ok(), self.clean_workspace(base))
            first = gate.phase_a()
            self.assertEqual("PHASE_A_READY", first.decision)
            self.assertIsNone(first.runtime_context_handle)
            self.assertIsNone(first.allowed_context_envelope)
            final = gate.phase_b()
            self.assertEqual(ALLOW_PHASE_B, final.decision)
            self.assertIsNotNone(final.runtime_context_handle)
            self.assertEqual(envelope, final.allowed_context_envelope)

    def test_releases_no_sensitive_context_before_all_gates_pass(self):
        with tempfile.TemporaryDirectory() as base:
            ws = self.clean_workspace(base)
            gate, authority, _envelope = build(lambda: measure_ok(), ws)
            denied = gate.phase_a()
            self.assertEqual("PHASE_A_READY", denied.decision)
            drifted = gate.phase_b()
            self.assertEqual(ALLOW_PHASE_B, drifted.decision)
            # A new gate whose provider qualification fails never releases anything.
            gate2, authority2, _ = build(lambda: measure_ok(provider_ok="false"), ws)
            result = gate2.phase_a()
            self.assertEqual(DENY_PROVIDER_IDENTITY, result.decision)
            self.assertIsNone(result.runtime_context_handle)
            self.assertIsNone(result.allowed_context_envelope)

    def test_claude_md_present_at_phase_a_denies(self):
        with tempfile.TemporaryDirectory() as base:
            ws = self.clean_workspace(base)
            (ws / "CLAUDE.md").write_text("rule", encoding="utf-8")
            gate, _authority, _envelope = build(lambda: measure_ok(), ws)
            result = gate.phase_a()
            self.assertEqual(DENY_PROJECT_INSTRUCTIONS, result.decision)
            self.assertIsNone(result.runtime_context_handle)
            self.assertIsNone(result.allowed_context_envelope)

    def test_claude_md_appears_between_phase_a_and_phase_b_denies(self):
        with tempfile.TemporaryDirectory() as base:
            ws = self.clean_workspace(base)
            gate, authority, _envelope = build(lambda: measure_ok(), ws)
            self.assertEqual("PHASE_A_READY", gate.phase_a().decision)
            (ws / ".claude").mkdir()
            (ws / ".claude" / "CLAUDE.md").write_text("rule", encoding="utf-8")
            result = gate.phase_b()
            self.assertEqual(DENY_PROJECT_INSTRUCTIONS, result.decision)
            self.assertEqual({}, authority._issued)

    def _drift_case(self, field):
        with tempfile.TemporaryDirectory() as base:
            ws = self.clean_workspace(base)
            calls = {"count": 0}

            def measure():
                calls["count"] += 1
                if calls["count"] == 1:
                    return measure_ok()
                return measure_ok(**{field: "changed"})

            gate, authority, _envelope = build(measure, ws)
            self.assertEqual("PHASE_A_READY", gate.phase_a().decision)
            result = gate.phase_b()
            self.assertEqual(DENY_CARRIED_STATE_DRIFT, result.decision)
            self.assertIn(field, result.carried_state_mismatches)
            self.assertIsNone(result.runtime_context_handle)
            self.assertEqual({}, authority._issued)

    def test_provider_changes_between_phase_a_and_phase_b_denies(self):
        self._drift_case("provider_principal")

    def test_model_changes_between_phase_a_and_phase_b_denies(self):
        self._drift_case("effective_model_id")

    def test_endpoint_changes_between_phase_a_and_phase_b_denies(self):
        self._drift_case("endpoint_policy_digest")

    def test_auth_store_changes_between_phase_a_and_phase_b_denies(self):
        self._drift_case("config_root_digest")

    def test_carried_state_mismatch_denies(self):
        self._drift_case("harness_binary_identity")

    def test_runtime_authority_loss_before_phase_b_denies(self):
        with tempfile.TemporaryDirectory() as base:
            gate, authority, _envelope = build(lambda: measure_ok(), self.clean_workspace(base), authority_alive=lambda: False)
            self.assertEqual("PHASE_A_READY", gate.phase_a().decision)
            result = gate.phase_b()
            self.assertEqual(DENY_RUNTIME_AUTHORITY_LOST, result.decision)
            self.assertEqual({}, authority._issued)

    def test_launcher_loss_before_phase_b_denies(self):
        with tempfile.TemporaryDirectory() as base:
            gate, _authority, _envelope = build(lambda: measure_ok(), self.clean_workspace(base), launcher_alive=lambda: False)
            self.assertEqual("PHASE_A_READY", gate.phase_a().decision)
            self.assertEqual(DENY_RUNTIME_AUTHORITY_LOST, gate.phase_b().decision)

    def test_containment_not_verified_denies(self):
        with tempfile.TemporaryDirectory() as base:
            gate, _authority, _envelope = build(lambda: measure_ok(containment_ok="false"), self.clean_workspace(base))
            self.assertEqual(DENY_CONTAINMENT, gate.phase_a().decision)

    def test_observation_incomplete_denies(self):
        with tempfile.TemporaryDirectory() as base:
            gate, _authority, _envelope = build(lambda: {"provider_ok": "true"}, self.clean_workspace(base))
            self.assertEqual(DENY_OBSERVATION_INCOMPLETE, gate.phase_a().decision)

    def test_scan_incomplete_denies_sensitive(self):
        with tempfile.TemporaryDirectory() as base:
            missing = Path(base) / "missing"
            gate, _authority, _envelope = build(lambda: measure_ok(), missing)
            self.assertEqual(DENY_OBSERVATION_INCOMPLETE, gate.phase_a().decision)
            self.assertEqual(DENY_OBSERVATION_INCOMPLETE, gate.phase_b().decision)

    def test_phase_a_cwd_is_neutral_and_has_no_handle(self):
        with tempfile.TemporaryDirectory() as base:
            gate, _authority, _envelope = build(lambda: measure_ok(), self.clean_workspace(base))
            result = gate.phase_a()
            self.assertIsNone(result.runtime_context_handle)
            self.assertIsNone(result.allowed_context_envelope)

    def test_phase_a_environment_contains_no_sensitive_credentials(self):
        with tempfile.TemporaryDirectory() as base:
            calls = []

            def measure():
                calls.append({})
                return measure_ok()

            gate, _authority, _envelope = build(measure, self.clean_workspace(base))
            gate.phase_a()
            gate.phase_b()
            self.assertEqual([{}, {}], calls)

    def test_runtime_handle_issued_only_after_final_admission(self):
        with tempfile.TemporaryDirectory() as base:
            ws = self.clean_workspace(base)
            calls = {"count": 0}

            def measure():
                calls["count"] += 1
                return measure_ok(**({"effective_model_id": "changed"} if calls["count"] > 1 else {}))

            gate, authority, _envelope = build(measure, ws)
            gate.phase_a()
            gate.phase_b()
            self.assertEqual({}, authority._issued)