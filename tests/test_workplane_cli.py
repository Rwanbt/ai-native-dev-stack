import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_workplane_authority import GovernedWork


def cli(*arguments, expect=0):
    process = subprocess.run([sys.executable, "-m", "ainative_workplane", *[str(argument) for argument in arguments]], capture_output=True, text=True)
    assert process.returncode == expect, f"exit {process.returncode} (expected {expect}): {process.stderr or process.stdout}"
    return json.loads(process.stdout) if process.stdout.strip() else None


class WorkCommandTests(unittest.TestCase):
    def test_work_new_then_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            created = cli("work", "new", directory, "--artifact", 'notes={"done":false}')
            self.assertEqual(1, created["revision"])
            self.assertEqual(created, cli("work", "validate", directory))


class AuthoritativeCliTests(unittest.TestCase):
    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def test_verify_then_converge_from_committed_state_alone(self):
        work = self.governed()
        record = cli("verify", "--work", work.work, "--verification", work.specification_uid, "--repo", work.repo)
        self.assertEqual("PASS", record["result"])
        self.assertEqual("verification_run", record["schema_name"])

        converged = cli("converge", "--work", work.work, "--repo", work.repo, expect=0)
        self.assertEqual("CONVERGED", converged["verdict"])
        self.assertTrue(converged["observed_provenance"]["git_recorded"])
        self.assertTrue(converged["evidence"][0]["eligible"])

    def test_a_failing_verification_moves_the_exit_code_to_one(self):
        work = self.governed()
        failing = "import sys\nprint('Ran 1 test in 0.0s')\nprint('FAILED (failures=1)')\nsys.exit(1)\n"
        (work.repo / "tests" / "check.py").write_text(failing, encoding="utf-8")
        subprocess.run(["git", "-C", str(work.repo), "commit", "-am", "break the check"], check=True, capture_output=True)
        blocked = cli("converge", "--work", work.work, "--repo", work.repo, expect=1)
        self.assertEqual("NOT_CONVERGED", blocked["verdict"])
        self.assertIn("VERIFICATION_FAILED", blocked["evidence"][0]["reasons"])

    def test_the_authoritative_commands_take_no_contract_policy_or_root(self):
        help_text = subprocess.run([sys.executable, "-m", "ainative_workplane", "converge", "--help"], capture_output=True, text=True).stdout
        for forbidden in ("--contract", "--policy", "--approval-root", "--freshness", "--evidence"):
            self.assertNotIn(forbidden, help_text, f"converge still accepts {forbidden} from its caller")

    def test_the_loose_helper_is_reachable_only_under_debug_and_says_so(self):
        work = self.governed()
        registry = work.root / "registry.json"
        registry.write_text(json.dumps(work.registry()), encoding="utf-8")
        binding = work.root / "binding.json"
        binding.write_text(json.dumps({
            "work": {"uid": work.approval_root["uid"].replace("root_", "work_"), "digest": "a" * 64}, "contract_revision": 1,
            "contract_digest": "a" * 64, "verification_specification": {"uid": work.specification_uid, "digest": "a" * 64},
            "command_registry_digest": __import__("ainative_workplane").canonical_digest(work.registry()),
            "policy_digest": "a" * 64, "approval_root": {"uid": work.approval_root["uid"], "digest": "a" * 64},
            "repository_snapshot": {"uid": work.specification_uid.replace("verify_", "snapshot_"), "digest": "a" * 64},
            "snapshot_content_digest": "a" * 64, "snapshot_dependency_digest": "a" * 64, "snapshot_head": "0" * 40,
            "producer": "debug", "producer_version": "1", "evidence_provenance": "SIGNED",
        }), encoding="utf-8")
        result = cli("debug", "run-command", "--registry", registry, "--binding", binding, "--command", "check", "--cwd", work.repo)
        self.assertEqual("none", result["authority"], "the loose helper must never present itself as authority")
        self.assertEqual("PASS", result["record"]["result"])


if __name__ == "__main__":
    unittest.main()
