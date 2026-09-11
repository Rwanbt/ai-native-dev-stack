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

class RealStoreIsolationTests(unittest.TestCase):
    def store_root(self, directory: str) -> Path:
        root = Path(directory) / "stores"
        root.mkdir(exist_ok=True)
        return root

    def write_store(self, root: Path, namespace, payload: str = "notes") -> Path:
        path = namespace_path(root, namespace)
        path.mkdir(parents=True, exist_ok=True)
        header = StoreHeader(STORE_HEADER_SCHEMA_VERSION, namespace.namespace_digest)
        (path / "header.json").write_text(header.encode() + payload + "\n", encoding="utf-8")
        return path

    def read_header(self, path: Path) -> StoreHeader:
        content = (path / "header.json").read_text(encoding="utf-8")
        first_line, _separator, _rest = content.partition("\n")
        return StoreHeader.decode(first_line)

    def test_real_store_loads_only_for_its_exact_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.store_root(directory)
            current = namespace("company-a")
            path = self.write_store(root, current)
            self.assertEqual("LOAD", admit_load(self.read_header(path), current).decision)

    def test_copied_store_under_a_foreign_namespace_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.store_root(directory)
            foreign = namespace("company-b")
            path = self.write_store(root, foreign, payload="foreign notes")
            self.assertEqual("REFUSE", admit_load(self.read_header(path), namespace("company-a")).decision)

    def test_stale_digest_requires_recorded_migration_not_auto_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.store_root(directory)
            stale = namespace_for(domain("company-a"), envelope("repo"), memory_policy("global"), assurance())
            path = self.write_store(root, stale)
            current = namespace("company-a")
            header = self.read_header(path)
            self.assertEqual("REFUSE", admit_load(header, current).decision)
            plan = plan_migration(header, current)
            self.assertIsNotNone(plan)
            migrated = apply_migration(plan, operator_approval_reference="decision-2026-09-11")
            self.assertEqual("LOAD", admit_load(migrated, current).decision)
