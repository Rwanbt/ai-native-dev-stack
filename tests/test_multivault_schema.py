import unittest
from ainative.multivault.schema import AllowedContextEnvelope, SecurityDomain, SecurityEpoch, persistence_namespace, policy_digest

class MultiVaultSchemaTests(unittest.TestCase):
    def test_domain_digest_is_order_independent_and_excludes_runtime(self):
        domain = SecurityDomain("company-a", "vault-a", "project-a", "operator-a")
        self.assertEqual(domain.identity_digest(), SecurityDomain("company-a", "vault-a", "project-a", "operator-a").identity_digest())
    def test_epoch_change_changes_digest(self):
        self.assertNotEqual(SecurityEpoch("a", "1", "x").digest(), SecurityEpoch("a", "2", "x").digest())
    def test_policy_digest_normalizes_mapping_order(self):
        self.assertEqual(policy_digest({"a": 1, "b": 2}), policy_digest({"b": 2, "a": 1}))
    def test_envelope_and_namespace_are_order_independent_but_exact_match(self):
        first = AllowedContextEnvelope(("repo-b", "repo-a"), ("vault",))
        second = AllowedContextEnvelope(("repo-a", "repo-b"), ("vault",))
        self.assertEqual(first.exposure_digest(), second.exposure_digest())
        domain = SecurityDomain("a", "v", "p", "o")
        self.assertNotEqual(persistence_namespace(domain, first.exposure_digest(), "m", "x"), persistence_namespace(domain, first.exposure_digest(), "m", "y"))
