"""Trust onboarding: a scaffold a user can produce, refusals without tracebacks.

The `{}` case is the regression: bootstrap.py read `approval_root["uid"]` and
raised a bare KeyError, whose traceback exited 1 - the code the Work Plane
contract reserves for NOT_CONVERGED. A malformed document is INVALID (2), with
a stable code both a human and a script can read.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative_workplane import cli as workplane_cli
from ainative_workplane.bootstrap import bootstrap
from ainative_workplane.trust_schema import (POLICY_CODE, ROOT_CODE, UNSUPPORTED_CODE,
                                             TrustSchemaError, scaffold_approval_root,
                                             scaffold_policy, validate_approval_root,
                                             validate_policy)


def cli_capture(arguments: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = workplane_cli.main(arguments)
    return code, out.getvalue(), err.getvalue()


class ScaffoldValidation(unittest.TestCase):

    def test_the_scaffold_satisfies_the_validators_bootstrap_applies(self):
        policy = scaffold_policy()
        root = scaffold_approval_root(policy, initialized_by="someone")
        self.assertIs(validate_policy(policy), policy)
        self.assertIs(validate_approval_root(root), root)

    def test_an_empty_root_is_invalid_not_unsupported(self):
        with self.assertRaises(TrustSchemaError) as raised:
            validate_approval_root({})
        self.assertEqual(raised.exception.code, ROOT_CODE)

    def test_a_root_with_an_unknown_schema_is_unsupported(self):
        with self.assertRaises(TrustSchemaError) as raised:
            validate_approval_root({"schema_name": "something_else",
                                    "schema_version": 1})
        self.assertEqual(raised.exception.code, UNSUPPORTED_CODE)

    def test_an_unsupported_version_is_unsupported(self):
        policy = scaffold_policy()
        root = scaffold_approval_root(policy, initialized_by="someone")
        root["schema_version"] = 99
        with self.assertRaises(TrustSchemaError) as raised:
            validate_approval_root(root)
        self.assertEqual(raised.exception.code, UNSUPPORTED_CODE)

    def test_a_root_digest_that_does_not_commit_is_refused(self):
        policy = scaffold_policy()
        root = scaffold_approval_root(policy, initialized_by="someone")
        root["bootstrap"]["initialized_by"] = "someone else"
        with self.assertRaises(TrustSchemaError) as raised:
            validate_approval_root(root)
        self.assertEqual(raised.exception.code, ROOT_CODE)
        self.assertIn("root_digest", raised.exception.message)

    def test_a_policy_digest_that_does_not_commit_is_refused(self):
        policy = scaffold_policy()
        policy["promotion_policy"] = "changed after the commitment"
        with self.assertRaises(TrustSchemaError) as raised:
            validate_policy(policy)
        self.assertEqual(raised.exception.code, POLICY_CODE)

    def test_an_unknown_predicate_names_the_known_ones(self):
        with self.assertRaises(TrustSchemaError) as raised:
            scaffold_policy(predicate_id="vibes")
        self.assertEqual(raised.exception.code, UNSUPPORTED_CODE)
        self.assertIn("recorded_owner_ack", raised.exception.message)

    def test_bootstrap_refuses_a_predicate_the_policy_does_not_configure(self):
        directory = tempfile.TemporaryDirectory(prefix="trust-onboarding-")
        self.addCleanup(directory.cleanup)
        repo = Path(directory.name)
        policy = scaffold_policy(predicate_id="recorded_owner_ack")
        root = scaffold_approval_root(policy, initialized_by="someone")
        with self.assertRaises(TrustSchemaError) as raised:
            bootstrap(repo, approval_root=root, policy=policy,
                      initialized_by="someone", predicate_id="signature")
        self.assertEqual(raised.exception.code, POLICY_CODE)


class CliRefusals(unittest.TestCase):
    """Exit code 2, a stable code on stderr, the same record as JSON."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="trust-cli-")
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True,
                       capture_output=True)

    def empty(self, name: str, payload: str) -> Path:
        path = self.repo / name
        path.write_text(payload, encoding="utf-8")
        return path

    def test_the_empty_document_refuses_with_a_stable_code(self):
        document = self.empty("empty.json", "{}")
        code, out, err = cli_capture([
            "trust", "bootstrap", "--repo", str(self.repo),
            "--approval-root", str(document), "--policy", str(document),
            "--by", "tester"])
        self.assertEqual(code, 2)
        self.assertIn("refused:", err)
        self.assertNotIn("Traceback", err + out)
        record = json.loads(out)
        self.assertEqual(record["error"], ROOT_CODE)

    def test_a_missing_file_refuses_with_the_root_code(self):
        missing = self.repo / "missing.json"
        code, out, err = cli_capture([
            "trust", "bootstrap", "--repo", str(self.repo),
            "--approval-root", str(missing), "--policy", str(missing),
            "--by", "tester"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["error"], ROOT_CODE)

    def test_trust_init_writes_a_usable_scaffold_and_claims_no_authority(self):
        code, out, err = cli_capture([
            "trust", "init", "--repo", str(self.repo), "--by", "tester"])
        self.assertEqual(code, 0, err)
        record = json.loads(out)
        self.assertTrue(record["authority"].startswith("none"))
        root = json.loads(Path(record["approval_root"]).read_text(encoding="utf-8"))
        policy = json.loads(Path(record["policy"]).read_text(encoding="utf-8"))
        validate_approval_root(root)
        validate_policy(policy)
        self.assertFalse((self.repo / ".ai-native" / "trust"
                          / "project_trust.json").exists(),
                         "trust init created an anchor; scaffolding is not authority")

    def test_trust_init_refuses_to_overwrite_without_force(self):
        cli_capture(["trust", "init", "--repo", str(self.repo), "--by", "tester"])
        code, out, err = cli_capture(["trust", "init", "--repo", str(self.repo),
                                      "--by", "tester"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["error"], "TRUST_SCAFFOLD_EXISTS")
        code, out, _ = cli_capture(["trust", "init", "--repo", str(self.repo),
                                    "--by", "tester", "--force"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()