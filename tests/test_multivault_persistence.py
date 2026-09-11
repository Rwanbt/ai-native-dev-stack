import json
import tempfile
import unittest
from pathlib import Path

from ainative.multivault.persistence import (
    STORE_HEADER_SCHEMA_VERSION,
    MigrationPlan,
    StoreHeader,
    admit_load,
    apply_migration,
    namespace_for,
    namespace_path,
    plan_migration,
)
from ainative.multivault.schema import (
    AllowedContextEnvelope,
    MemoryPolicyDigest,
    PersistenceAssuranceDigest,
    SecurityDomain,
)


def domain(name: str) -> SecurityDomain:
    return SecurityDomain(name, f"vault-{name}", f"project-{name}", f"operator-{name}")


def envelope(repository: str):
    return AllowedContextEnvelope((repository,), ("vault",))


def memory_policy(scope: str = "domain") -> MemoryPolicyDigest:
    return MemoryPolicyDigest({"scope": scope})


def assurance(profile: str = "GUARDED") -> PersistenceAssuranceDigest:
    return PersistenceAssuranceDigest(profile, "cloud", "local")


def namespace(name: str = "personal", repository: str = "repo", profile: str = "GUARDED"):
    return namespace_for(domain(name), envelope(repository), memory_policy(), assurance(profile))


class PersistenceIsolationTests(unittest.TestCase):
    def test_namespace_components_are_opaque_and_disjoint_across_domains(self):
        personal = namespace("personal")
        company = namespace("company-a")
        self.assertNotEqual(personal.namespace_digest, company.namespace_digest)
        self.assertNotEqual(personal.path_segments(), company.path_segments())
        self.assertTrue(all(len(segment) == 64 for segment in personal.path_segments()))

    def test_personal_memory_is_refused_for_company_a(self):
        header = StoreHeader(STORE_HEADER_SCHEMA_VERSION, namespace("personal").namespace_digest)
        decision = admit_load(header, namespace("company-a"))
        self.assertEqual("REFUSE", decision.decision)

    def test_company_a_memory_is_refused_for_company_b(self):
        header = StoreHeader(STORE_HEADER_SCHEMA_VERSION, namespace("company-a").namespace_digest)
        self.assertEqual("REFUSE", admit_load(header, namespace("company-b")).decision)

    def test_guarded_memory_is_never_auto_promoted_to_enforced(self):
        header = StoreHeader(STORE_HEADER_SCHEMA_VERSION, namespace(profile="GUARDED").namespace_digest)
        enforced = namespace(profile="ENFORCED-DIAGNOSTIC")
        self.assertEqual("REFUSE", admit_load(header, enforced).decision)
        self.assertIsNotNone(plan_migration(header, enforced))

    def test_exact_match_loads(self):
        current = namespace("company-a")
        header = StoreHeader(STORE_HEADER_SCHEMA_VERSION, current.namespace_digest)
        self.assertEqual("LOAD", admit_load(header, current).decision)

    def test_unsupported_header_schema_fails_closed(self):
        current = namespace()
        header = StoreHeader(STORE_HEADER_SCHEMA_VERSION + 1, current.namespace_digest)
        self.assertEqual("REFUSE", admit_load(header, current).decision)

    def test_header_roundtrips_through_json(self):
        header = StoreHeader(STORE_HEADER_SCHEMA_VERSION, namespace().namespace_digest)
        self.assertEqual(header, StoreHeader.decode(header.encode()))

    def test_corrupt_header_fails_closed(self):
        payloads = (
            "{not json",
            json.dumps({"schema_version": 99, "namespace_digest": "x"}),
            json.dumps({"schema_version": 1}),
        )
        for payload in payloads:
            with self.assertRaises(ValueError):
                StoreHeader.decode(payload)

    def test_migration_requires_an_explicit_operator_approval_reference(self):
        plan = MigrationPlan("from", "to")
        with self.assertRaises(ValueError):
            apply_migration(plan, operator_approval_reference="")
        new_header = apply_migration(plan, operator_approval_reference="decision-2026-09-11")
        self.assertEqual("to", new_header.namespace_digest)

    def test_no_migration_plan_for_an_exact_match(self):
        current = namespace("company-a")
        header = StoreHeader(STORE_HEADER_SCHEMA_VERSION, current.namespace_digest)
        self.assertIsNone(plan_migration(header, current))

    def test_namespace_path_uses_the_four_opaque_segments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = namespace()
            self.assertEqual(root.joinpath(*current.path_segments()), namespace_path(root, current))