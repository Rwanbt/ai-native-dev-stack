"""Materialization APIs: owners transform authoritative values into typed objects."""
import unittest

from ainative.multivault.harness_claude import (
    QUALIFICATION_FLAGS,
    _CONTRACT_FIELDS,
    measurement_from_probe_evidence,
)
from ainative.multivault.runtime_authority import authority_from_operator_state
from ainative.multivault.schema import (
    SecurityEpoch,
    allowed_context_envelope_from_authoritative_roots,
)
from ainative.multivault.sensitive_launch import CARRIED_STATE_FIELDS


def envelope():
    return allowed_context_envelope_from_authoritative_roots(("C:/repo",), ("C:/vault",))


def operator_state(**overrides):
    values = dict(
        security_domain_id="company-a",
        vault_identity="vault-a",
        checkout_identity="checkout-a",
        project_security_id="project-a",
        classification="PERSONAL",
        allowed_context_envelope=envelope(),
        security_epoch=SecurityEpoch("company-a", "1", "1"),
        approved_model_egress_digest="egress",
        memory_policy_digest="memory",
        persistence_assurance_digest="persistence",
        execution_profile="profile",
        runtime_observation_policy_digest="observation",
    )
    values.update(overrides)
    return values


def evidence(**overrides):
    values = {field: "value" for field in _CONTRACT_FIELDS}
    values.update({flag: True for flag in QUALIFICATION_FLAGS})
    values.update(overrides)
    return values


class EnvelopeMaterializationTests(unittest.TestCase):
    def test_exact_authoritative_roots_materialize_unchanged(self):
        built = allowed_context_envelope_from_authoritative_roots(("A",), ("B",))
        self.assertEqual(("A",), built.repository_roots)
        self.assertEqual(("B",), built.vault_memory_roots)

    def test_missing_authoritative_root_fails_closed(self):
        with self.assertRaises(ValueError):
            allowed_context_envelope_from_authoritative_roots((), ("B",))
        with self.assertRaises(ValueError):
            allowed_context_envelope_from_authoritative_roots(("A",), ())


class AuthorityMaterializationTests(unittest.TestCase):
    def test_operator_state_materializes_to_runtime_authority(self):
        authority = authority_from_operator_state(**operator_state())
        self.assertEqual("company-a", authority.state.security_domain_id)
        self.assertEqual("PERSONAL", authority.state.classification)
        self.assertTrue(authority.state.authority_instance_id)

    def test_missing_digest_fails_closed(self):
        with self.assertRaises(ValueError):
            authority_from_operator_state(**operator_state(memory_policy_digest=""))
        with self.assertRaises(ValueError):
            authority_from_operator_state(**operator_state(classification=""))


class MeasurementMaterializationTests(unittest.TestCase):
    def test_real_evidence_materializes_gate_compatible_keys(self):
        measured = measurement_from_probe_evidence(evidence())
        expected = set(CARRIED_STATE_FIELDS) | set(QUALIFICATION_FLAGS)
        self.assertEqual(expected, set(measured))

    def test_absent_field_stays_absent(self):
        values = evidence()
        del values["harness_version"]
        measured = measurement_from_probe_evidence(values)
        self.assertNotIn("harness_version", measured)

    def test_flag_passes_only_on_explicit_true(self):
        self.assertEqual("false", measurement_from_probe_evidence(evidence(provider_ok=False))["provider_ok"])
        values = evidence()
        del values["containment_ok"]
        measured = measurement_from_probe_evidence(values)
        self.assertNotIn("containment_ok", measured)

    def test_unknown_fields_never_elevate(self):
        measured = measurement_from_probe_evidence(evidence(provider_ok_override=True))
        self.assertNotIn("provider_ok_override", measured)

    def test_non_mapping_evidence_is_empty(self):
        self.assertEqual({}, measurement_from_probe_evidence(None))


if __name__ == "__main__":
    unittest.main()
