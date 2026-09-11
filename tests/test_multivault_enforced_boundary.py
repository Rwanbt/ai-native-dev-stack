import sys
import tempfile
import time
import unittest
from pathlib import Path

from ainative.multivault.enforced_boundary import (
    ACL_DENIED,
    ACL_GRANTED,
    BOUNDARY_REVOKED,
    BOUNDARY_VALID,
    BoundaryEvidence,
    boundary_digest,
    evaluate_acl_for_sid,
    resolve_principal_sid,
    verify_boundary,
)

CURRENT_NAME = "ainative-enforced"


class EnforcedBoundaryTests(unittest.TestCase):
    def test_missing_principal_resolves_to_none(self):
        self.assertIsNone(resolve_principal_sid("ainative-enforced-definitely-absent"))

    @unittest.skipUnless(sys.platform.startswith("win"), "Windows SID resolution")
    def test_current_user_sid_resolves(self):
        import getpass
        sid = resolve_principal_sid(getpass.getuser())
        self.assertIsNotNone(sid)
        self.assertTrue(sid.startswith("S-1-5-21-"))

    @unittest.skipUnless(sys.platform.startswith("win"), "Windows ACL semantics")
    def test_acl_of_a_path_without_the_sid_is_denied_by_absence(self):
        with tempfile.TemporaryDirectory() as directory:
            verdict = evaluate_acl_for_sid(directory, "S-1-5-21-0-0-0-9999")
            self.assertEqual(ACL_DENIED, verdict)

    def test_missing_path_is_unreadable(self):
        from ainative.multivault.enforced_boundary import ACL_UNREADABLE
        self.assertEqual(ACL_UNREADABLE, evaluate_acl_for_sid("C:/definitely/missing/path-xyz", "S-1-5-18"))

    def test_stale_evidence_revokes_the_boundary(self):
        now = time.monotonic()
        evidence = (
            BoundaryEvidence("principal", "net user", "poll", now - 3600, 300, "d1"),
        )
        verdict = verify_boundary(evidence, {"principal": 300}, now=now)
        self.assertEqual(BOUNDARY_REVOKED, verdict.decision)
        self.assertTrue(any("stale" in reason for reason in verdict.reasons))

    def test_missing_property_revokes_the_boundary(self):
        now = time.monotonic()
        verdict = verify_boundary((), {"vault_acl": 60}, now=now)
        self.assertEqual(BOUNDARY_REVOKED, verdict.decision)
        self.assertTrue(any("missing" in reason for reason in verdict.reasons))

    def test_fresh_complete_evidence_validates_and_digest_tracks_changes(self):
        now = time.monotonic()
        first = (BoundaryEvidence("vault_acl", "icacls", "per_operation", now, 60, "d1"),)
        second = (BoundaryEvidence("vault_acl", "icacls", "per_operation", now, 60, "d2"),)
        self.assertEqual(BOUNDARY_VALID, verify_boundary(first, {"vault_acl": 60}, now=now).decision)
        self.assertNotEqual(boundary_digest(first), boundary_digest(second))

    def test_declared_max_age_beyond_policy_revokes(self):
        now = time.monotonic()
        evidence = (BoundaryEvidence("principal", "net user", "poll", now, 9999, "d1"),)
        verdict = verify_boundary(evidence, {"principal": 300}, now=now)
        self.assertEqual(BOUNDARY_REVOKED, verdict.decision)