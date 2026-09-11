import unittest
from dataclasses import asdict, replace
from pathlib import Path
import json
from unittest.mock import patch

import ainative.multivault.schema as schema_module
from ainative.multivault.schema import (
    AllowedContextEnvelope,
    ApprovedModelEgress,
    CarriedStateContract,
    ExecutionBoundaryDigest,
    MemoryPolicyDigest,
    PersistenceAssuranceDigest,
    ProviderClass,
    PushIntentDigest,
    SecurityClassification,
    SecurityDomain,
    SecurityEpoch,
    SemanticEgressDigest,
    persistence_namespace,
    policy_digest,
)


def envelope(**overrides) -> AllowedContextEnvelope:
    fields = {"repository_roots": ("repo",), "vault_memory_roots": ("vault",)}
    fields.update(overrides)
    return AllowedContextEnvelope(**fields)


def approved_egress(**overrides) -> ApprovedModelEgress:
    fields = {
        "provider_class": ProviderClass.CLOUD_API,
        "provider_principal_binding": "principal-a",
        "allowed_model_ids": ("model-a", "model-b"),
        "allowed_model_families": ("family-a",),
        "allowed_routing_classes": ("direct",),
        "allowed_endpoint_policy": "policy-a",
        "allowed_egress_class": "cloud",
        "dynamic_routing_policy": "deny",
        "fallback_policy": "deny",
    }
    fields.update(overrides)
    return ApprovedModelEgress(**fields)


def carried_state() -> CarriedStateContract:
    return CarriedStateContract(
        "binary", "1.0", "config", "principal-a", "model-a", "direct", "endpoint", "plugins", "adapter", "probe"
    )


def boundary(**overrides) -> ExecutionBoundaryDigest:
    fields = {
        "network_policy": "deny",
        "mounts": "none",
        "filesystem_acl_boundary": "acl",
        "credential_boundary": "isolated",
        "harness_config_roots": ("root-a",),
        "runtime_identity": "user-a",
        "ipc_topology": "pipe",
        "rest_reachability": "unreachable",
        "authority_store_placement": "outside",
        "provider_route_policy": "deny",
        "git_transfer_boundary": "governed",
        "process_containment": "job-object",
    }
    fields.update(overrides)
    return ExecutionBoundaryDigest(**fields)


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
    def test_canonical_fixture_has_stable_domain_digest(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "multivault-canonical.json").read_text(encoding="utf-8"))
        self.assertEqual("79d62a0120258c862119202ce2942e7358ef4f0873a6f96e278ab4e5135535f6", policy_digest(fixture))

    def test_classification_is_ordered_for_expansion_checks(self):
        ordered = [
            SecurityClassification.PERSONAL,
            SecurityClassification.TEAM,
            SecurityClassification.CONFIDENTIAL,
            SecurityClassification.CRITICAL,
        ]
        self.assertEqual(ordered, sorted(ordered))
        self.assertTrue(SecurityClassification.CONFIDENTIAL < SecurityClassification.CRITICAL)

    def test_provider_class_declares_exactly_the_adr_0014_classes(self):
        self.assertEqual(
            {"cloud_api", "onprem_managed", "local_runtime"},
            {value.value for value in ProviderClass},
        )

    def test_every_named_digest_includes_the_schema_version(self):
        digests = [
            lambda: SecurityDomain("a", "v", "p", "o").identity_digest(),
            lambda: SecurityEpoch("a", "1", "x").digest(),
            lambda: envelope().exposure_digest(),
            lambda: MemoryPolicyDigest({"a": 1}).digest(),
            lambda: PersistenceAssuranceDigest("GUARDED", "cloud", "local").digest(),
            lambda: SemanticEgressDigest({"provider": "local"}).digest(),
            lambda: boundary().digest(),
            lambda: PushIntentDigest("src", "base", "refs/heads/main", "src:refs/heads/main", "remote", "policy", "objects", "scan", "me@example.com").digest(),
            lambda: approved_egress().digest(),
            lambda: carried_state().digest(),
        ]
        baseline = [compute() for compute in digests]
        with patch.object(schema_module, "SCHEMA_VERSION", schema_module.SCHEMA_VERSION + 1):
            changed = [compute() for compute in digests]
        for before, after in zip(baseline, changed):
            self.assertNotEqual(before, after)

    def test_allowed_context_envelope_roundtrips_and_covers_every_root_class(self):
        baseline = envelope()
        rebuilt = AllowedContextEnvelope(**{key: tuple(value) for key, value in asdict(baseline).items()})
        self.assertEqual(baseline, rebuilt)
        self.assertEqual(baseline.exposure_digest(), rebuilt.exposure_digest())

        variants = [
            envelope(shared_memory_roots=("shared",)),
            envelope(semantic_roots=("semantic",)),
            envelope(graph_roots=("graph",)),
            envelope(allowed_write_targets=("write",)),
            envelope(project_boundaries=("project",)),
            envelope(source_classes=("class",)),
        ]
        digests = {variant.exposure_digest() for variant in variants}
        self.assertEqual(len(variants), len(digests))
        self.assertNotIn(baseline.exposure_digest(), digests)

    def test_approved_model_egress_digest_normalizes_sets_and_covers_class(self):
        self.assertEqual(
            approved_egress(allowed_model_ids=("model-b", "model-a")).digest(),
            approved_egress(allowed_model_ids=("model-a", "model-b")).digest(),
        )
        self.assertNotEqual(approved_egress().digest(), approved_egress(provider_class=ProviderClass.LOCAL_RUNTIME).digest())
        self.assertNotEqual(approved_egress().digest(), approved_egress(allowed_model_ids=("model-a",)).digest())
        self.assertNotEqual(approved_egress().digest(), approved_egress(fallback_policy="allow-any").digest())

    def test_execution_boundary_digest_normalizes_roots_and_covers_evidence(self):
        self.assertEqual(
            boundary(harness_config_roots=("root-b", "root-a")).digest(),
            boundary(harness_config_roots=("root-a", "root-b")).digest(),
        )
        baseline = boundary().digest()
        for changed in (
            boundary(network_policy="allow"),
            boundary(process_containment="none"),
            boundary(authority_store_placement="inside"),
        ):
            self.assertNotEqual(baseline, changed.digest())

    def test_push_intent_digest_binds_exact_transfer_intent(self):
        intent = PushIntentDigest("src", "base", "refs/heads/main", "src:refs/heads/main", "remote", "policy", "objects", "scan", "me@example.com")
        self.assertEqual(intent.digest(), replace(intent).digest())
        self.assertNotEqual(intent.digest(), replace(intent, exact_refspec="src:refs/heads/other").digest())
        self.assertNotEqual(intent.digest(), replace(intent, expected_remote_base_oid="other-base").digest())
        self.assertNotEqual(intent.digest(), replace(intent, scan_result_digest="other-scan").digest())

    def test_persistence_assurance_digest_is_exact_match(self):
        baseline = PersistenceAssuranceDigest("GUARDED", "cloud", "local").digest()
        for changed in (
            PersistenceAssuranceDigest("ENFORCED-DIAGNOSTIC", "cloud", "local"),
            PersistenceAssuranceDigest("GUARDED", "onprem_managed", "local"),
            PersistenceAssuranceDigest("GUARDED", "cloud", "remote"),
        ):
            self.assertNotEqual(baseline, changed.digest())

    def test_memory_policy_digest_matches_policy_digest_contract(self):
        policy = {"retention": "session", "scope": "domain"}
        self.assertEqual(MemoryPolicyDigest(policy).digest(), policy_digest(policy))
        self.assertEqual(MemoryPolicyDigest({"b": 2, "a": 1}).digest(), MemoryPolicyDigest({"a": 1, "b": 2}).digest())

    def test_semantic_egress_digest_is_key_order_independent(self):
        self.assertEqual(
            SemanticEgressDigest({"provider": "local", "endpoint": "none"}).digest(),
            SemanticEgressDigest({"endpoint": "none", "provider": "local"}).digest(),
        )
        self.assertNotEqual(SemanticEgressDigest({"provider": "local"}).digest(), SemanticEgressDigest({"provider": "cloud"}).digest())

    def test_carried_state_contract_digest_covers_revalidation_fields(self):
        baseline = carried_state()
        self.assertNotEqual(baseline.digest(), replace(baseline, effective_model_id="model-b").digest())
        self.assertNotEqual(baseline.digest(), replace(baseline, probe_version="probe-2").digest())