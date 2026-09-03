import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative_workplane.contracts import canonical_digest, generate_uid
from ainative_workplane.trust import approval_root_commitment, policy_commitment

DIGEST = "a" * 64
HEAD = "0" * 40


def cli(*arguments, expect=0):
    process = subprocess.run([sys.executable, "-m", "ainative_workplane", *[str(argument) for argument in arguments]], capture_output=True, text=True)
    assert process.returncode == expect, f"exit {process.returncode} (expected {expect}): {process.stderr or process.stdout}"
    return json.loads(process.stdout) if process.stdout.strip() else None


def write(path, payload):
    Path(path).write_text(json.dumps(payload), encoding="utf-8")
    return path


class WorkCommandTests(unittest.TestCase):
    def test_work_new_then_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            created = cli("work", "new", directory, "--artifact", 'notes={"done":false}')
            self.assertEqual(1, created["revision"])
            self.assertEqual(created, cli("work", "validate", directory))


class VerifyAndConvergeTests(unittest.TestCase):
    def fixture(self, root: Path, *, argv, unverified_second_specification=False):
        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": argv, "timeout_seconds": 20, "substance": {"type": "exit_only", "minimum_observations": 0}}}}
        policy = {
            "schema_name": "project_policy", "schema_version": 1,
            "approval_predicate": {"predicate_id": "local", "policy_digest": DIGEST},
            "success_condition_mutation_provenance": "LOCAL_UNTRUSTED",
            "verification_evidence_provenance": "LOCAL_UNTRUSTED",
            "waiver_approval_rule": {"predicate_id": "local", "policy_digest": DIGEST},
            "human_approval_rule": {"predicate_id": "local", "policy_digest": DIGEST},
            "promotion_policy": "explicit",
        }
        commitment = policy_commitment(policy)
        for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
            policy[field]["policy_digest"] = commitment
        approval_root = {"schema_name": "approval_root", "schema_version": 1, "uid": generate_uid("root"), "root_digest": DIGEST, "policy_digest": commitment, "root_provenance": "LOCAL_UNTRUSTED", "bootstrap": {"initialized_at": "2026-09-02T00:00:00Z", "initialized_by": "cli-test"}}
        approval_root["root_digest"] = approval_root_commitment(approval_root)

        specification = generate_uid("verify")
        criteria = [{"uid": "ac-1", "requirement": {"uid": "req-1", "digest": DIGEST}, "verification_specifications": [{"uid": specification, "digest": DIGEST}]}]
        specifications = [{"uid": specification, "relationship": "direct_scope", "covered_implementation_paths": ["src/**"]}]
        acceptance_refs = [{"uid": "ac-1", "digest": DIGEST}]
        if unverified_second_specification:
            second = generate_uid("verify")
            criteria.append({"uid": "ac-2", "requirement": {"uid": "req-1", "digest": DIGEST}, "verification_specifications": [{"uid": second, "digest": DIGEST}]})
            specifications.append({"uid": second, "relationship": "direct_scope", "covered_implementation_paths": ["src/**"]})
            acceptance_refs.append({"uid": "ac-2", "digest": DIGEST})
        contract = {
            "requirements": [{"uid": "req-1", "acceptance_criteria": acceptance_refs}],
            "acceptance_criteria": criteria,
            "tasks": [{"uid": "task-1", "requirements": [{"uid": "req-1", "digest": DIGEST}], "implementation_paths": ["src/app.py"]}],
            "verification_specifications": specifications,
        }
        binding = {
            "work": {"uid": generate_uid("work"), "digest": DIGEST}, "contract_revision": 1, "contract_digest": DIGEST,
            "verification_specification": {"uid": specification, "digest": DIGEST},
            "command_registry_digest": canonical_digest(registry), "policy_digest": commitment,
            "approval_root": {"uid": approval_root["uid"], "digest": approval_root["root_digest"]},
            "repository_snapshot": {"uid": generate_uid("snapshot"), "digest": DIGEST},
            "snapshot_content_digest": DIGEST, "snapshot_dependency_digest": DIGEST, "snapshot_head": HEAD,
            "producer": "cli-test", "producer_version": "1", "evidence_provenance": "LOCAL_UNTRUSTED",
        }
        return {
            "registry": write(root / "registry.json", registry),
            "policy": write(root / "policy.json", policy),
            "root": write(root / "root.json", approval_root),
            "contract": write(root / "contract.json", contract),
            "binding": write(root / "binding.json", binding),
        }

    def test_verify_reports_the_run_and_converge_maps_verdicts_to_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = self.fixture(root, argv=[sys.executable, "-c", "print('verified')"])

            record = cli("verify", "--registry", files["registry"], "--binding", files["binding"], "--command", "check", "--cwd", directory, "--require-substance")
            self.assertEqual("PASS", record["result"])
            self.assertEqual("verification_run", record["schema_name"])
            evidence = write(root / "evidence.json", record)
            freshness = write(root / "freshness.json", {
                "contract_digest": record["contract_digest"], "repository_snapshot": record["repository_snapshot"],
                "command_registry_digest": record["command_registry_digest"], "policy_digest": record["policy_digest"],
                "approval_root": record["approval_root"], "snapshot_head": record["snapshot_head"],
            })

            converged = cli("converge", "--contract", files["contract"], "--evidence", evidence, "--freshness", freshness, "--policy", files["policy"], "--approval-root", files["root"], expect=0)
            self.assertEqual("CONVERGED", converged["verdict"])

            # Without a freshness evaluation the engine cannot decide, and says so.
            invalid = cli("converge", "--contract", files["contract"], "--evidence", evidence, "--policy", files["policy"], "--approval-root", files["root"], expect=2)
            self.assertEqual("INVALID", invalid["verdict"])
            self.assertIn("FRESHNESS_UNAVAILABLE", [gap["code"] for gap in invalid["gaps"]])

    def test_a_declared_specification_without_evidence_exits_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = self.fixture(root, argv=[sys.executable, "-c", "print('verified')"], unverified_second_specification=True)
            record = cli("verify", "--registry", files["registry"], "--binding", files["binding"], "--command", "check", "--cwd", directory)
            evidence = write(root / "evidence.json", record)
            freshness = write(root / "freshness.json", {
                "contract_digest": record["contract_digest"], "repository_snapshot": record["repository_snapshot"],
                "command_registry_digest": record["command_registry_digest"], "policy_digest": record["policy_digest"],
                "approval_root": record["approval_root"], "snapshot_head": record["snapshot_head"],
            })
            blocked = cli("converge", "--contract", files["contract"], "--evidence", evidence, "--freshness", freshness, "--policy", files["policy"], "--approval-root", files["root"], expect=1)
            self.assertEqual("NOT_CONVERGED", blocked["verdict"])
            self.assertIn("UNVERIFIED_SPECIFICATION", [gap["code"] for gap in blocked["gaps"]])

    def test_a_failing_verification_exits_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = self.fixture(root, argv=[sys.executable, "-c", "raise SystemExit(3)"])
            record = cli("verify", "--registry", files["registry"], "--binding", files["binding"], "--command", "check", "--cwd", directory, expect=1)
            self.assertEqual("FAIL", record["result"])
            self.assertEqual(3, record["exit_code"])


if __name__ == "__main__":
    unittest.main()
