import unittest

from ainative.multivault.schema import SecurityClassification
from ainative.multivault.semantic import (
    ObservationStatus,
    SemanticObservation,
    SemanticProviderProfile,
    admit_semantic_session,
    semantic_revocation,
)


def profile(**overrides) -> SemanticProviderProfile:
    fields = {
        "plugin": "smart-connections",
        "plugin_version": "4.7.2",
        "provider": "local",
        "endpoint": "none",
        "indexing_mode": "file-change",
        "background_behavior": "none-observed",
        "store_location": ".smart-env",
        "observer_available": True,
        "egress_config_digest": "egress-1",
        "evidence_digest": "evidence-1",
    }
    fields.update(overrides)
    return SemanticProviderProfile(**fields)


SENSITIVE_CLASSES = (
    SecurityClassification.TEAM,
    SecurityClassification.CONFIDENTIAL,
    SecurityClassification.CRITICAL,
)


class SemanticAdmissionTests(unittest.TestCase):
    def test_personal_classification_allows_without_observer_requirement(self):
        self.assertEqual("ALLOW", admit_semantic_session(None, SecurityClassification.PERSONAL).decision)

    def test_sensitive_classifications_deny_without_a_profile(self):
        for classification in SENSITIVE_CLASSES:
            self.assertEqual("DENY", admit_semantic_session(None, classification).decision)

    def test_sensitive_classifications_deny_without_probe_qualified_profile(self):
        for classification in SENSITIVE_CLASSES:
            self.assertEqual("DENY", admit_semantic_session(profile(observer_available=False), classification).decision)
            self.assertEqual("DENY", admit_semantic_session(profile(evidence_digest=""), classification).decision)

    def test_sensitive_classifications_deny_without_a_trusted_egress_digest(self):
        for classification in SENSITIVE_CLASSES:
            self.assertEqual("DENY", admit_semantic_session(profile(), classification).decision)

    def test_sensitive_classifications_deny_on_egress_config_mismatch(self):
        result = admit_semantic_session(profile(), SecurityClassification.CONFIDENTIAL, approved_egress_digest="other")
        self.assertEqual("DENY", result.decision)

    def test_qualified_profile_with_approved_egress_allows_sensitive(self):
        for classification in SENSITIVE_CLASSES:
            result = admit_semantic_session(profile(), classification, approved_egress_digest="egress-1")
            self.assertEqual("ALLOW", result.decision)


class SemanticDriftTests(unittest.TestCase):
    def test_unchanged_observation_with_matching_digest_does_not_revoke(self):
        observation = SemanticObservation(ObservationStatus.UNCHANGED, "egress-1")
        self.assertIsNone(semantic_revocation("egress-1", observation))

    def test_changed_status_revokes_even_with_matching_digest(self):
        observation = SemanticObservation(ObservationStatus.CHANGED, "egress-1")
        self.assertIsNotNone(semantic_revocation("egress-1", observation))

    def test_digest_mismatch_revokes(self):
        observation = SemanticObservation(ObservationStatus.UNCHANGED, "egress-2")
        self.assertIsNotNone(semantic_revocation("egress-1", observation))

    def test_unreadable_configuration_revokes(self):
        observation = SemanticObservation(ObservationStatus.CONFIGURATION_UNREADABLE)
        self.assertIsNotNone(semantic_revocation("egress-1", observation))

    def test_unavailable_observer_revokes(self):
        observation = SemanticObservation(ObservationStatus.OBSERVER_UNAVAILABLE)
        self.assertIsNotNone(semantic_revocation("egress-1", observation))

    def test_missing_recorded_digest_revokes(self):
        observation = SemanticObservation(ObservationStatus.UNCHANGED, "egress-1")
        self.assertIsNotNone(semantic_revocation("", observation))