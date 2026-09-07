"""V3.3.1 trust: receipt model, validation, per-section health, E2E AU-AY."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import evidence as evidencelib
from ainative.knowledge import promotion as promotionlib
from ainative.knowledge import review as reviewlib
from ainative.knowledge import store as storelib
from ainative.knowledge import trust as trustlib
from ainative.knowledge.candidate import capture
from ainative.knowledge.errors import KnowledgeError

GIT = shutil.which("git")
needs_git = unittest.skipUnless(GIT, "git executable required")


def _write(project: Path, relative: str, content: str) -> Path:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


def _ready(project: Path, claim: str = "A durable rule.") -> dict:
    stored = storelib.append(project, capture(
        project=str(project), agent="opencode", session="sess-1",
        origin_type="user_correction", kind="PROJECT_RULE", claim=claim))
    reviewlib.classify_candidate(project, stored["candidate_id"],
                                 kind="PROJECT_RULE", actor="tester")
    evidencelib.add_evidence(project, stored["candidate_id"],
                             {"type": "USER_CONFIRMATION", "locator": "session"},
                             actor="tester")
    reviewlib.verify_candidate(project, stored["candidate_id"], actor="tester")
    return storelib.set_status(project, stored["candidate_id"],
                               "READY_FOR_PROMOTION", actor="tester")


def _git(project: Path, *args: str) -> None:
    subprocess.run([GIT, "-C", str(project), *args], check=True,
                   capture_output=True)


def _git_repo(project: Path) -> None:
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "t@t.t")
    _git(project, "config", "user.name", "t")
    _git(project, "add", "-A")
    _git(project, "commit", "-qm", "seed")


class ReceiptTest(unittest.TestCase):
    def test_Digest_BindsEveryField(self):
        base = {"decision_id": "kc_1", "target": "AGENTS.md",
                "operation": "ADD", "scope": {}, "base_digest": "b",
                "intended_result_digest": "r"}
        first = trustlib.approval_digest(**base)
        for key in base:
            altered = dict(base)
            altered[key] = "x"
            self.assertNotEqual(trustlib.approval_digest(**altered), first)
        self.assertEqual(trustlib.approval_digest(**base), first)

    def test_Ceremony_CannotClaimVerifiedEvidence(self):
        with self.assertRaises(KnowledgeError) as caught:
            trustlib.build_receipt(mode=trustlib.TRUSTED_OPERATOR_CEREMONY,
                                   capability_status="SEPARATED",
                                   evidence_status=trustlib.VERIFIED_WORKPLANE_AUTHORITY,
                                   approval_digest_value="d")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")

    def test_Verified_NeedsAuthorityRef(self):
        with self.assertRaises(KnowledgeError):
            trustlib.build_receipt(mode=trustlib.VERIFIED_WORKPLANE_AUTHORITY,
                                   capability_status="SEPARATED",
                                   evidence_status=trustlib.VERIFIED_WORKPLANE_AUTHORITY,
                                   approval_digest_value="d")

    def test_Derive_Matrix(self):
        ceremony = trustlib.build_receipt(
            mode=trustlib.TRUSTED_OPERATOR_CEREMONY, capability_status="SEPARATED",
            evidence_status=trustlib.UNVERIFIED_CEREMONY, approval_digest_value="d")
        self.assertEqual(trustlib.derive_qualification(ceremony), "UNVERIFIED")
        attested = trustlib.build_receipt(
            mode=trustlib.EXTERNAL_ATTESTATION, capability_status="UNKNOWN",
            evidence_status=trustlib.EXTERNALLY_ATTESTED,
            approval_digest_value="d", attestation_ref="board:42")
        self.assertEqual(trustlib.derive_qualification(attested),
                         "EXTERNALLY_ATTESTED")
        bare = dict(attested)
        bare["attestation_ref"] = None
        self.assertEqual(trustlib.derive_qualification(bare), "INVALID")
        verified = trustlib.build_receipt(
            mode=trustlib.VERIFIED_WORKPLANE_AUTHORITY, capability_status="SEPARATED",
            evidence_status=trustlib.VERIFIED_WORKPLANE_AUTHORITY,
            approval_digest_value="d", authority_ref="wp:root:1")
        self.assertEqual(trustlib.derive_qualification(verified), "INVALID")
        self.assertEqual(trustlib.derive_qualification(
            verified, verify=lambda ref, digest: True), "VERIFIED_WORKPLANE")
        self.assertEqual(trustlib.derive_qualification(
            verified, verify=lambda ref, digest: False), "INVALID")

        def _boom(ref, digest):
            raise RuntimeError("verifier down")

        self.assertEqual(trustlib.derive_qualification(verified, verify=_boom),
                         "INVALID")

    def test_ProductionRule_EvidenceOnly(self):
        self.assertTrue(trustlib.production_trust_qualified("VERIFIED_WORKPLANE"))
        self.assertTrue(trustlib.production_trust_qualified("EXTERNALLY_ATTESTED"))
        self.assertFalse(trustlib.production_trust_qualified("UNVERIFIED"))
        self.assertFalse(trustlib.production_trust_qualified("INVALID"))

    def test_Validate_BadVerified_Raises(self):
        verified = trustlib.build_receipt(
            mode=trustlib.VERIFIED_WORKPLANE_AUTHORITY, capability_status="SEPARATED",
            evidence_status=trustlib.VERIFIED_WORKPLANE_AUTHORITY,
            approval_digest_value="d", authority_ref="wp:x")
        with self.assertRaises(KnowledgeError) as caught:
            trustlib.validate_receipt(verified, verify=lambda r, d: False)
        self.assertEqual(caught.exception.code, "KNOWLEDGE_APPROVAL_INVALID")


class EndToEndTrustTest(unittest.TestCase):
    def test_AU_ForgedVerifiedClaim_InvalidButHealthy(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            ready = _ready(project)
            promotionlib.apply_promotion(project, ready["candidate_id"],
                                         operation="ADD", actor="tester")
            audit_path = (project / ".ai-native" / "knowledge" / "audit.jsonl")
            lines = audit_path.read_text(encoding="utf-8").splitlines()
            forged = []
            for line in lines:
                event = json.loads(line)
                if event.get("operation") == "PROMOTE":
                    event["detail"]["approval"]["evidence_status"] = \
                        "VERIFIED_WORKPLANE_AUTHORITY"
                    event["detail"]["approval"]["authority_ref"] = "wp:forged"
                forged.append(json.dumps(event, sort_keys=True))
            audit_path.write_text("\n".join(forged) + "\n", encoding="utf-8")
            full = promotionlib.describe_full(
                project, ready["candidate_id"],
                verify=lambda ref, digest: False)
            self.assertEqual(full["representation_health"], "HEALTHY")
            self.assertEqual(full["trust_qualification"], "INVALID")
            self.assertFalse(trustlib.production_trust_qualified(
                full["trust_qualification"]))

    def test_AV_Ceremony_Triple(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            ready = _ready(project)
            outcome = promotionlib.apply_promotion(project, ready["candidate_id"],
                                                   operation="ADD", actor="tester")
            self.assertEqual(outcome["trust_qualification"], "UNVERIFIED")
            full = promotionlib.describe_full(project, ready["candidate_id"])
            self.assertEqual((full["lifecycle_state"],
                              full["representation_health"],
                              full["trust_qualification"]),
                             ("PROMOTED", "HEALTHY", "UNVERIFIED"))

    def test_AW_VerifiedApproval_FreshClone(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            ready = _ready(project)
            outcome = promotionlib.apply_promotion(
                project, ready["candidate_id"], operation="ADD", actor="op",
                approval={"mode": "VERIFIED_WORKPLANE_AUTHORITY",
                          "capability_status": "SEPARATED",
                          "evidence_status": "VERIFIED_WORKPLANE_AUTHORITY",
                          "authority_ref": "wp:manifest:abc"},
                verify=lambda ref, digest: ref == "wp:manifest:abc")
            self.assertEqual(outcome["trust_qualification"], "VERIFIED_WORKPLANE")
            expected = outcome["approval"]["approval_digest"]
            clone = Path(directory) / "clone"
            shutil.copytree(project, clone,
                            ignore=shutil.ignore_patterns(".git"))
            self.assertFalse((clone / ".ai-native" / "knowledge" / "transient").exists())
            full = promotionlib.describe_full(
                clone, ready["candidate_id"],
                verify=lambda ref, digest: ref == "wp:manifest:abc"
                and digest == expected)
            self.assertEqual((full["lifecycle_state"],
                              full["representation_health"],
                              full["trust_qualification"]),
                             ("PROMOTED", "HEALTHY", "VERIFIED_WORKPLANE"))

    def test_AX_ReplayedDigest_Rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            ready = _ready(project)
            outcome = promotionlib.apply_promotion(
                project, ready["candidate_id"], operation="ADD", actor="op",
                approval={"mode": "VERIFIED_WORKPLANE_AUTHORITY",
                          "capability_status": "SEPARATED",
                          "evidence_status": "VERIFIED_WORKPLANE_AUTHORITY",
                          "authority_ref": "wp:manifest:abc"},
                verify=lambda ref, digest: True)
            digest = outcome["approval"]["approval_digest"]
            replayed = dict(outcome["approval"])
            replayed["approval_digest"] = digest + "tampered"
            self.assertEqual(trustlib.derive_qualification(
                replayed, verify=lambda ref, d: True), "VERIFIED_WORKPLANE")
            self.assertEqual(trustlib.derive_qualification(
                replayed, verify=lambda ref, d: d == digest), "INVALID")

    @needs_git
    def test_AY_SupersededSpan_UnrelatedEditHealthy(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            _write(project, "notes.md", "# Notes\n")
            _git_repo(project)
            ready = _ready(project, claim="Adopt the new retry policy.")
            promotionlib.apply_promotion(project, ready["candidate_id"],
                                         operation="ADD", actor="tester")
            _git(project, "add", "-A")
            _git(project, "commit", "-qm", "promote R")
            _write(project, "notes.md", "# Notes\n\nUnrelated.\n")
            _git(project, "add", "-A")
            _git(project, "commit", "-qm", "unrelated notes")
            full = promotionlib.describe_full(project, ready["candidate_id"])
            self.assertEqual(full["representation_health"], "HEALTHY")
            agents = (project / "AGENTS.md").read_text(encoding="utf-8")
            agents = agents.replace("Adopt the new retry policy.",
                                    "Adopt the newest retry policy.")
            _write(project, "AGENTS.md", agents)
            _git(project, "add", "-A")
            _git(project, "commit", "-qm", "refine retry section")
            full = promotionlib.describe_full(project, ready["candidate_id"])
            self.assertEqual(full["representation_health"], "SUPERSEDED")

    @needs_git
    def test_RevertedSpan_Detected(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            _git_repo(project)
            ready = _ready(project, claim="Adopt the new retry policy.")
            promotionlib.apply_promotion(project, ready["candidate_id"],
                                         operation="ADD", actor="tester")
            _git(project, "add", "-A")
            _git(project, "commit", "-qm", "promote R")
            agents = (project / "AGENTS.md").read_text(encoding="utf-8")
            marker = "### Adopt the new retry policy."
            self.assertIn(marker, agents)
            _write(project, "AGENTS.md", "# Rules\n")
            _git(project, "add", "-A")
            _git(project, "commit", "-qm", "Revert promote R")
            full = promotionlib.describe_full(project, ready["candidate_id"])
            self.assertEqual(full["representation_health"], "REVERTED")

    def test_AmbiguousSpan_Detected(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            ready = _ready(project, claim="Adopt the new retry policy.")
            promotionlib.apply_promotion(project, ready["candidate_id"],
                                         operation="ADD", actor="tester")
            target = project / "AGENTS.md"
            raw = target.read_bytes()
            target.write_bytes(raw + b"\n### Adopt the new retry policy.\n- copy\n")
            full = promotionlib.describe_full(project, ready["candidate_id"])
            self.assertEqual(full["representation_health"], "AMBIGUOUS")

    def test_CrlfDuplicate_StillAmbiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            target = _write(project, "AGENTS.md", "# Rules\n")
            ready = _ready(project, claim="Adopt the new retry policy.")
            promotionlib.apply_promotion(project, ready["candidate_id"],
                                         operation="ADD", actor="tester")
            raw = target.read_bytes()
            target.write_bytes(raw + b"\r\n### Adopt the new retry policy.\r\n- copy\r\n")
            full = promotionlib.describe_full(project, ready["candidate_id"])
            self.assertEqual(full["representation_health"], "AMBIGUOUS")

    def test_MissingTarget_Detected(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            target = _write(project, "AGENTS.md", "# Rules\n")
            ready = _ready(project, claim="Adopt the new retry policy.")
            promotionlib.apply_promotion(project, ready["candidate_id"],
                                         operation="ADD", actor="tester")
            target.unlink()
            full = promotionlib.describe_full(project, ready["candidate_id"])
            self.assertEqual(full["representation_health"], "MISSING")


if __name__ == "__main__":
    unittest.main()