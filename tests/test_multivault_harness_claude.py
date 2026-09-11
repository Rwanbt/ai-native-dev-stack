import unittest

from ainative.multivault.capability import (
    CapabilityManifest,
    CapabilityRegistry,
    ControlLevel,
    Observation,
    ObservationMode,
    TwoPhaseAttestation,
)
from ainative.multivault.harness_claude import (
    CLAUDE_CODE_TUPLE,
    build_manifest,
    parse_model_usage,
)

REAL_PAYLOAD = '{"is_error":false,"modelUsage":{"claude-haiku-4-5-20251001":{"canonicalModel":"claude-haiku-4-5","provider":"firstParty","inputTokens":531}}}'


class ModelUsageParserTests(unittest.TestCase):
    def test_parses_the_versioned_effective_model(self):
        parsed = parse_model_usage(REAL_PAYLOAD)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual("claude-haiku-4-5-20251001", parsed["model_id"])
        self.assertEqual("claude-haiku-4-5", parsed["canonical_model"])
        self.assertEqual("firstParty", parsed["provider"])

    def test_rejects_malformed_or_ambiguous_payloads(self):
        self.assertIsNone(parse_model_usage("not json"))
        self.assertIsNone(parse_model_usage('{"modelUsage": {}}'))
        self.assertIsNone(parse_model_usage('{"modelUsage": {"a": {"canonicalModel": "x", "provider": "y"}, "b": {"canonicalModel": "x", "provider": "y"}}}'))


class ClaudeManifestTests(unittest.TestCase):
    def test_current_evidence_keeps_the_tuple_ineligible(self):
        manifest = build_manifest("evidence-digest")
        self.assertFalse(manifest.sensitive_eligible())
        registry = CapabilityRegistry()
        registry.register(manifest)
        self.assertEqual("DENY", registry.sensitive_admission(CLAUDE_CODE_TUPLE))

    def test_fully_attested_manifest_is_eligible(self):
        manifest = CapabilityManifest(
            capability_tuple=CLAUDE_CODE_TUPLE,
            provider_selection_control=ControlLevel.VERIFIED,
            model_selection_control=ControlLevel.VERIFIED,
            endpoint_routing_control=ControlLevel.VERIFIED,
            provider_principal_observation=Observation(ObservationMode.PER_OPERATION),
            model_identity_observation=Observation(ObservationMode.PER_OPERATION),
            endpoint_routing_observation=Observation(ObservationMode.PER_OPERATION),
            auth_store_observation=Observation(ObservationMode.EVENT),
            two_phase_attestation=TwoPhaseAttestation.PROBE,
            session_containment=ControlLevel.VERIFIED,
            evidence_digest="evidence-digest",
        )
        self.assertTrue(manifest.sensitive_eligible())