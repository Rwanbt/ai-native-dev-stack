import unittest

from ainative_workplane.contracts import (
    ContractError,
    canonical_digest,
    canonical_json_bytes,
    canonical_path,
    digest_bytes,
    generate_uid,
    validate_artifact,
    validate_case_collisions,
    validate_uid,
)


DIGEST = "a" * 64


def uid(prefix):
    return generate_uid(prefix, timestamp_ms=1_700_000_000_000, entropy=bytes(range(10)))


def reference(prefix):
    return {"uid": uid(prefix), "digest": DIGEST}


def artifact(name, **fields):
    return {"schema_name": name, "schema_version": 1, **fields}


class WorkPlaneContractsTests(unittest.TestCase):
    def assert_invalid(self, code, value):
        with self.assertRaises(ContractError) as caught:
            validate_artifact(value)
        self.assertEqual(code, caught.exception.code)

    def test_uid_is_prefixed_ulid_and_not_display_identifier(self):
        value = uid("req")
        self.assertEqual("req_01HF7YAT00000G40R40M30E209", value)
        self.assertEqual(value, validate_uid(value, "req"))
        with self.assertRaises(ContractError):
            validate_uid("REQ-001")

    def test_canonical_json_key_order_whitespace_and_unicode_are_stable(self):
        left = {"z": "café", "a": [2, 1]}
        right = {"a": [2, 1], "z": "cafe\u0301"}
        self.assertEqual(canonical_json_bytes(left), b'{"a":[2,1],"z":"caf\xc3\xa9"}')
        self.assertEqual(canonical_digest(left), canonical_digest(right))
        with self.assertRaises(ContractError):
            canonical_json_bytes({"ambiguous": 0.1})

    def test_file_digest_fixtures_are_portable(self):
        self.assertEqual("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", digest_bytes(b""))
        self.assertEqual(digest_bytes(b"plain text\n"), digest_bytes("plain text\n".encode("utf-8")))
        self.assertEqual("7b49b9e063bd91a4f9252b413261f5557b9c570aa61516989499f64a62dbcdd6", digest_bytes("caf\u00e9\n".encode("utf-8")))
        self.assertEqual("054edec1d0211f624fed0cbca9d4f9400b0e491c43742af2c5b0abebf0c990d8", digest_bytes(bytes([0, 1, 2, 3])))

    def test_paths_normalize_windows_separators_but_reject_escape_components(self):
        self.assertEqual("nested/.github/file.txt", canonical_path("nested\\.github\\file.txt"))
        self.assertEqual(".env.example", canonical_path(".env.example"))
        for invalid in ("../escape", "./local", "nested/../escape", "/absolute", "C:\\absolute"):
            with self.assertRaises(ContractError):
                canonical_path(invalid)
        with self.assertRaises(ContractError) as caught:
            validate_case_collisions(["src/Thing.py", "src/thing.py"])
        self.assertEqual("CASE_COLLISION", caught.exception.code)

    def test_valid_minimal_artifacts_cover_all_pr01_schema_identities(self):
        values = [
            artifact("work_manifest", work_uid=uid("work"), revision=1, artifacts={"policy": {"path": "revisions/1/policy.json", "digest": DIGEST}}, root_chain=[{"revision": 1, "digest": DIGEST}], policy_chain=[{"revision": 1, "digest": DIGEST}]),
            artifact("requirements", uid=uid("req"), statement="must work", acceptance_criteria=[reference("ac")]),
            artifact("acceptance_criteria", uid=uid("ac"), requirement=reference("req"), criterion="works", verification_specifications=[reference("verify")]),
            artifact("tasks", uid=uid("task"), requirements=[reference("req")], implementation_paths=["src/module.py"], status="planned"),
            artifact("verification_specification", uid=uid("verify"), acceptance_criteria=[reference("ac")], command_registry=reference("root"), relationship="black_box", execution_scope=["tests"], covered_implementation_paths=["src/module.py"], dependencies=[], substance_requirement="test result", required_evidence_provenance="GIT_REVIEWED"),
            artifact("project_policy", approval_predicate={"predicate_id": "review-v1", "policy_digest": DIGEST}, required_mutation_facts={"git_recorded": True}, required_evidence_facts={"git_recorded": True, "ci_verified": True}, waiver_approval_rule={"predicate_id": "waiver-v1", "policy_digest": DIGEST}, human_approval_rule={"predicate_id": "human-v1", "policy_digest": DIGEST}, promotion_policy="explicit"),
            artifact("approval_root", uid=uid("root"), root_digest=DIGEST, policy_digest=DIGEST, root_provenance="GIT_REVIEWED", bootstrap={"initialized_at": "2026-09-02T00:00:00Z", "initialized_by": "owner"}),
            artifact("waiver", uid=uid("waiver"), target=reference("gap"), reason="accepted risk", scope="one AC", approved_by="owner", approved_at="2026-09-02T00:00:00Z", state="proposed", approval_provenance="UNTRACKED", approval_predicate={"predicate_id": "waiver-v1", "policy_digest": DIGEST}, policy_digest=DIGEST),
            artifact("human_approval", uid=uid("approval"), target=reference("ac"), approved_by="owner", approved_at="2026-09-02T00:00:00Z", approval_provenance="GIT_REVIEWED", approval_predicate={"predicate_id": "human-v1", "policy_digest": DIGEST}, policy_digest=DIGEST),
            artifact("repository_snapshot", uid=uid("snapshot"), head="abc123", dirty=False, scope=["src/module.py"], dependency_paths=[], dependencies=[], content_digest=DIGEST, dependency_digest=DIGEST, command_registry_digest=DIGEST, policy_digest=DIGEST),
            artifact("verification_run", uid=uid("run"), work=reference("work"), contract_revision=1, contract_digest=DIGEST, verification_specification=reference("verify"), command_registry_digest=DIGEST, policy_digest=DIGEST, approval_root=reference("root"), repository_snapshot=reference("snapshot"), snapshot_content_digest=DIGEST, snapshot_dependency_digest=DIGEST, snapshot_head="0" * 40, producer="runtime", producer_version="1.0", evidence_provenance="CI_APPROVED", command="check", result="PASS", exit_code=0, started_at="2026-09-02T00:00:00Z", finished_at="2026-09-02T00:00:01Z", duration_ms=1000, stdout_digest=DIGEST, stderr_digest=DIGEST, substance_metadata={}),
            artifact("convergence_run", uid=uid("convergence"), work=reference("work"), policy_digest=DIGEST, registry_digest=DIGEST, approval_root=reference("root"), snapshot=reference("snapshot"), verification_runs=[reference("run")], gaps=[], verdict="pass", timestamp="2026-09-02T00:00:01Z", engine_version="1.0"),
        ]
        for value in values:
            with self.subTest(schema=value["schema_name"]):
                validate_artifact(value)

    def test_schema_validation_rejects_missing_unknown_malformed_and_invalid_values(self):
        self.assert_invalid("MISSING_REQUIRED_FIELD", artifact("requirements", uid=uid("req"), statement="missing refs"))
        self.assert_invalid("UNSUPPORTED_SCHEMA_VERSION", artifact("requirements", schema_version=2, uid=uid("req"), statement="x", acceptance_criteria=[]))
        self.assert_invalid("INVALID_UID", artifact("requirements", uid="REQ-001", statement="x", acceptance_criteria=[]))
        self.assert_invalid("INVALID_DIGEST", artifact("requirements", uid=uid("req"), statement="x", acceptance_criteria=[{"uid": uid("ac"), "digest": "bad"}]))
        self.assert_invalid("MISSING_REQUIRED_FIELD", artifact("requirements", uid=uid("req"), statement="x", acceptance_criteria=[{"uid": uid("ac")}]))
        invalid = artifact("verification_specification", uid=uid("verify"), acceptance_criteria=[], command_registry=reference("root"), relationship="custom", execution_scope=["tests"], covered_implementation_paths=[], dependencies=[], substance_requirement="x", required_evidence_provenance="GIT_REVIEWED")
        self.assert_invalid("INVALID_VERIFICATION_RELATIONSHIP", invalid)
        invalid["relationship"] = "direct_scope"
        invalid["required_evidence_provenance"] = "ARBITRARY"
        self.assert_invalid("INVALID_PROVENANCE", invalid)

    def test_trust_models_fail_closed(self):
        malformed_root = artifact("approval_root", uid=uid("root"), root_digest="bad", policy_digest=DIGEST, root_provenance="GIT_REVIEWED", bootstrap={"initialized_at": "now", "initialized_by": "owner"})
        self.assert_invalid("INVALID_DIGEST", malformed_root)
        invalid_waiver = artifact("waiver", uid=uid("waiver"), target=reference("gap"), reason="risk", scope="x", approved_by="agent", approved_at="now", state="effective", approval_provenance="UNTRACKED", approval_predicate={"predicate_id": "p", "policy_digest": DIGEST}, policy_digest=DIGEST)
        self.assert_invalid("INVALID_WAIVER_AUTHORITY", invalid_waiver)
        invalid_approval = artifact("human_approval", uid=uid("approval"), target=reference("ac"), approved_by="owner", approved_at="now", approval_provenance="GIT_REVIEWED", approval_predicate={"predicate_id": "p", "policy_digest": DIGEST}, policy_digest=DIGEST, approved=True)
        self.assert_invalid("INVALID_FIELD", invalid_approval)
        missing_predicate = artifact("human_approval", uid=uid("approval"), target=reference("ac"), approved_by="owner", approved_at="now", approval_provenance="GIT_REVIEWED", policy_digest=DIGEST)
        self.assert_invalid("MISSING_REQUIRED_FIELD", missing_predicate)


if __name__ == "__main__":
    unittest.main()
