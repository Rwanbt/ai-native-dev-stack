import unittest
from ainative.multivault.canary import DomainCanary, evaluate

class MultiVaultCanaryTests(unittest.TestCase):
    def test_all_cross_domain_pairs_are_denied(self):
        for source, requested in (("personal", "company-a"), ("company-a", "personal"), ("company-a", "company-b")):
            self.assertEqual("DENY", evaluate(DomainCanary(source, requested, "vault.read"))["verdict"])

    def test_same_domain_is_not_a_cross_domain_bypass(self):
        self.assertEqual("ALLOW", evaluate(DomainCanary("company-a", "company-a", "vault.read"))["verdict"])

    def test_missing_domain_fails_closed(self):
        self.assertEqual("DENY", evaluate(DomainCanary("", "company-a", "vault.read"))["verdict"])
