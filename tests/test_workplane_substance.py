import sys
import tempfile
import unittest

from ainative_workplane.contracts import canonical_digest, generate_uid
from ainative_workplane.runner import PREVIEW_CHARS, RunnerError, VerificationRunner, load_registry, redact
from ainative_workplane.substance import SubstanceError, evaluate, validate_contract

DIGEST = "a" * 64


def registry(**definition):
    return {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": definition}}


def binding(command_registry):
    reference = lambda prefix: {"uid": generate_uid(prefix), "digest": DIGEST}
    return {
        "work": reference("work"), "contract_revision": 1, "contract_digest": DIGEST,
        "verification_specification": reference("verify"),
        "command_registry_digest": canonical_digest(command_registry),
        "policy_digest": DIGEST, "approval_root": reference("root"),
        "repository_snapshot": reference("snapshot"), "snapshot_content_digest": DIGEST,
        "snapshot_dependency_digest": DIGEST, "snapshot_head": "0" * 40, "producer": "test", "producer_version": "1",
        "evidence_provenance": "LOCAL_UNTRUSTED",
    }


def run(command_registry, *, require_substance=True):
    with tempfile.TemporaryDirectory() as directory:
        return VerificationRunner(command_registry).run("check", cwd=directory, binding=binding(command_registry), require_substance=require_substance)


class SubstanceContractTests(unittest.TestCase):
    def test_contract_validation_is_closed(self):
        self.assertEqual({"type": "unittest", "minimum_observations": 1}, validate_contract({"type": "unittest"}))
        for invalid in ({"type": "junit"}, {"type": "unittest", "minimum_observations": -1}, {"type": "unittest", "minimum_observations": True}, {"type": "exit_only", "minimum_observations": 1}, "unittest"):
            with self.assertRaises(SubstanceError):
                validate_contract(invalid)

    def test_registry_rejects_an_unreadable_substance_contract(self):
        with self.assertRaisesRegex(RunnerError, "UNKNOWN_SUBSTANCE_ADAPTER"):
            load_registry(registry(argv=["echo"], substance={"type": "junit"}))
        with self.assertRaisesRegex(RunnerError, "INVALID_SUBSTANCE_CONTRACT"):
            load_registry(registry(argv=["echo"], substance={"type": "unittest", "minimum_observations": -2}))

    def test_undeclared_or_unreadable_substance_is_suspicious(self):
        self.assertEqual((True, {"substance": "undeclared"}), evaluate(None, stdout="", stderr="", exit_code=0))
        suspicious, metadata = evaluate({"type": "unittest"}, stdout="nothing recognisable", stderr="", exit_code=0)
        self.assertTrue(suspicious)
        self.assertFalse(metadata["parsed"])


class RunnerSubstanceTests(unittest.TestCase):
    def test_zero_tests_at_exit_zero_is_not_a_pass(self):
        empty = registry(argv=[sys.executable, "-c", "import sys; sys.stderr.write('Ran 0 tests in 0.001s\\n\\nOK\\n')"], timeout_seconds=10, substance={"type": "unittest", "minimum_observations": 1})
        self.assertEqual("SUSPICIOUS_VERIFICATION", run(empty).result)

        real = registry(argv=[sys.executable, "-c", "import sys; sys.stderr.write('Ran 4 tests in 0.010s\\n\\nOK\\n')"], timeout_seconds=10, substance={"type": "unittest", "minimum_observations": 1})
        evidence = run(real)
        self.assertEqual("PASS", evidence.result)
        self.assertEqual(4, evidence.artifact["substance_metadata"]["tests_executed"])

    def test_a_command_without_a_substance_contract_cannot_satisfy_required_verification(self):
        silent = registry(argv=[sys.executable, "-c", "print('done')"], timeout_seconds=10)
        self.assertEqual("SUSPICIOUS_VERIFICATION", run(silent).result)
        self.assertEqual("PASS", run(silent, require_substance=False).result)

    def test_structured_json_substance_counts_observations(self):
        empty = registry(argv=[sys.executable, "-c", "import json; print(json.dumps({'observations': 0}))"], timeout_seconds=10, substance={"type": "json", "minimum_observations": 1})
        self.assertEqual("SUSPICIOUS_VERIFICATION", run(empty).result)
        full = registry(argv=[sys.executable, "-c", "import json; print(json.dumps({'observations': 7}))"], timeout_seconds=10, substance={"type": "json", "minimum_observations": 1})
        evidence = run(full)
        self.assertEqual("PASS", evidence.result)
        self.assertEqual(7, evidence.artifact["substance_metadata"]["observations"])


class RedactionTests(unittest.TestCase):
    def test_common_credential_shapes_are_masked(self):
        for secret, marker in (
            ("Authorization: Bearer abc.def-123", "abc.def-123"),
            ("Set-Cookie: session=deadbeef; Path=/", "deadbeef"),
            ("ghp_0123456789abcdefghij", "ghp_0123456789abcdefghij"),
            ("github_pat_01234567890123456789abc", "github_pat_01234567890123456789abc"),
            ("sk-abcdefghijklmnopqrst", "sk-abcdefghijklmnopqrst"),
            ("xoxb-1234567890-abcdef", "xoxb-1234567890-abcdef"),
            ("AKIAQ7B3CDEFGHIJKLMN", "AKIAQ7B3CDEFGHIJKLMN"),
            ('{"token":"abc123456"}', "abc123456"),
            ("password = hunter2", "hunter2"),
            ("-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----", "MIIE"),
        ):
            self.assertNotIn(marker, redact(secret), f"unredacted: {secret!r}")
        self.assertEqual("nothing to hide here", redact("nothing to hide here"))

    def test_persisted_evidence_redacts_and_bounds_the_preview(self):
        noisy = registry(argv=[sys.executable, "-c", "print('token=supersecretvalue'); print('x' * 900)"], timeout_seconds=10, max_output_bytes=100_000, substance={"type": "exit_only", "minimum_observations": 0})
        evidence = run(noisy)
        preview = evidence.artifact["substance_metadata"]["stdout_preview"]
        self.assertNotIn("supersecretvalue", preview)
        self.assertIn("[REDACTED]", preview)
        self.assertLessEqual(len(preview), PREVIEW_CHARS)


if __name__ == "__main__":
    unittest.main()
