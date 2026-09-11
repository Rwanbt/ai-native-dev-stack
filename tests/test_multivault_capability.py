import unittest

from ainative.multivault.capability import (
    CapabilityManifest,
    CapabilityRegistry,
    CapabilityTuple,
    ControlLevel,
    Observation,
    ObservationMode,
    TwoPhaseAttestation,
)


def manifest(**overrides: object) -> CapabilityManifest:
    values: dict[str, object] = {
        "capability_tuple": CapabilityTuple("codex", "1.0", "cloud_api", "windows", "1.0", "1.0"),
        "provider_selection_control": ControlLevel.VERIFIED,
        "model_selection_control": ControlLevel.VERIFIED,
        "endpoint_routing_control": ControlLevel.VERIFIED,
        "provider_principal_observation": Observation(ObservationMode.EVENT),
        "model_identity_observation": Observation(ObservationMode.PER_OPERATION),
        "endpoint_routing_observation": Observation(ObservationMode.POLL, 30),
        "auth_store_observation": Observation(ObservationMode.EVENT),
        "two_phase_attestation": TwoPhaseAttestation.PROBE,
        "session_containment": ControlLevel.VERIFIED,
        "evidence_digest": "verified-probe-evidence",
    }
    values.update(overrides)
    return CapabilityManifest(**values)  # type: ignore[arg-type]


class CapabilityManifestTests(unittest.TestCase):
    def test_unknown_tuple_never_inherits_another_versions_capability(self):
        registry = CapabilityRegistry()
        registry.register(manifest())
        unknown = CapabilityTuple("codex", "1.1", "cloud_api", "windows", "1.0", "1.0")
        self.assertEqual("DENY", registry.sensitive_admission(unknown))

    def test_partial_or_unobserved_assertion_denies_sensitive_admission(self):
        registry = CapabilityRegistry()
        registry.register(manifest(session_containment=ControlLevel.PARTIAL))
        self.assertEqual("DENY", registry.sensitive_admission(manifest().capability_tuple))
        registry.register(manifest(model_identity_observation=Observation(ObservationMode.NONE)))
        self.assertEqual("DENY", registry.sensitive_admission(manifest().capability_tuple))

    def test_only_complete_probe_backed_tuple_is_admitted(self):
        registry = CapabilityRegistry()
        qualified = manifest()
        registry.register(qualified)
        self.assertEqual("ALLOW", registry.sensitive_admission(qualified.capability_tuple))
