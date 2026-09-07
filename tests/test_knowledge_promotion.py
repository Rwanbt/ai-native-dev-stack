"""K4a gates: target resolution, planned patches, atomic promotion, reconcile."""

from __future__ import annotations

import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from ainative.knowledge import promotion as promotionlib
from ainative.knowledge import review as reviewlib
from ainative.knowledge import store as storelib
from ainative.knowledge import targets as targetslib
from ainative.knowledge.candidate import capture
from ainative.knowledge import evidence as evidencelib
from ainative.knowledge.errors import KnowledgeError


def _ready(project: Path, claim: str = "Integration tests use the real database.",
           kind: str = "PROJECT_RULE") -> dict:
    stored = storelib.append(project, capture(
        project=str(project), agent="opencode", session="sess-1",
        origin_type="user_correction", kind=kind, claim=claim))
    reviewlib.classify_candidate(project, stored["candidate_id"], kind=kind,
                                 actor="tester")
    evidencelib.add_evidence(project, stored["candidate_id"],
                             {"type": "USER_CONFIRMATION", "locator": "session"},
                             actor="tester")
    reviewlib.verify_candidate(project, stored["candidate_id"], actor="tester")
    return storelib.set_status(project, stored["candidate_id"],
                               "READY_FOR_PROMOTION", actor="tester")


def _write(project: Path, relative: str, content: str) -> Path:
    """Write exact bytes: `Path.write_text` translates newlines on Windows."""

    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


class ResolveTest(unittest.TestCase):
    def test_Resolve_ProjectRule_SelectsAgentsMd(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _ready(project)
            self.assertEqual(targetslib.resolve(project, stored).name, "AGENTS.md")

    def test_Resolve_AmbiguousAiContext_RefusedWithCandidates(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "a/AI_CONTEXT.md", "# A\n")
            _write(project, "b/AI_CONTEXT.md", "# B\n")
            stored = _ready(project, kind="MODULE_INVARIANT")
            with self.assertRaises(KnowledgeError) as caught:
                targetslib.resolve(project, stored)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_TARGET_UNSUPPORTED")

    def test_Resolve_ExplicitTarget_Wins(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "a/AI_CONTEXT.md", "# A\n")
            _write(project, "b/AI_CONTEXT.md", "# B\n")
            stored = _ready(project, kind="MODULE_INVARIANT")
            resolved = targetslib.resolve(project, stored, target="b/AI_CONTEXT.md")
            self.assertEqual((resolved.parent.name, resolved.name), ("b", "AI_CONTEXT.md"))

    def test_Resolve_TraversalTarget_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _ready(project)
            with self.assertRaises(KnowledgeError) as caught:
                targetslib.resolve(project, stored, target="../../escape.md")
            self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_LOCATOR")

    def test_Resolve_VaultHint_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _ready(project, kind="RESEARCH_KNOWLEDGE")
            with self.assertRaises(KnowledgeError) as caught:
                targetslib.resolve(project, stored)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_TARGET_UNSUPPORTED")


class PlanApplyTest(unittest.TestCase):
    def test_Plan_AddPreviewsWithoutWriting(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _ready(project)
            plan = promotionlib.plan_promotion(project, stored["candidate_id"],
                                               operation="ADD", actor="tester")
            self.assertEqual(plan["base_digest"],
                             sha256(b"# Rules\n").hexdigest())
            self.assertTrue(plan["diff_preview"])
            self.assertEqual((project / "AGENTS.md").read_text(encoding="utf-8"),
                             "# Rules\n")
            self.assertEqual(storelib.inspect_candidate(
                project, stored["candidate_id"])["status"], "READY_FOR_PROMOTION")

    def test_Apply_AddWritesAndPromotes(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _ready(project)
            outcome = promotionlib.apply_promotion(project, stored["candidate_id"],
                                                   operation="ADD", actor="tester")
            body = (project / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Integration tests use the real database.", body)
            self.assertIn(stored["candidate_id"], body)
            self.assertEqual(storelib.inspect_candidate(
                project, stored["candidate_id"])["status"], "PROMOTED")
            promotes = [event for event in storelib.read_audit(project)
                        if event["operation"] == "PROMOTE"]
            self.assertEqual(len(promotes), 1)
            self.assertEqual(promotes[0]["detail"]["base_digest"], outcome["base_digest"])
            self.assertEqual(promotes[0]["detail"]["result_digest"],
                             outcome["result_digest"])

    def test_Apply_StaleBase_RefusesBeforeWriting(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _ready(project)
            plan = promotionlib.plan_promotion(project, stored["candidate_id"],
                                               operation="ADD", actor="tester")
            _write(project, "AGENTS.md", "# Rules\n\n# Human edit\n")
            with self.assertRaises(KnowledgeError) as caught:
                promotionlib.apply_promotion(project, stored["candidate_id"],
                                             operation="ADD", actor="tester",
                                             expect_base=plan["base_digest"])
            self.assertEqual(caught.exception.code, "KNOWLEDGE_STALE_BASE")
            self.assertIn("Human edit",
                          (project / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertEqual(storelib.inspect_candidate(
                project, stored["candidate_id"])["status"], "READY_FOR_PROMOTION")

    def test_Apply_ConcurrentChange_Refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _ready(project)
            promotionlib.plan_promotion(project, stored["candidate_id"],
                                        operation="ADD", actor="tester")
            _write(project, "AGENTS.md", "# Rules\n\n# Racing agent\n")
            with self.assertRaises(KnowledgeError) as caught:
                promotionlib.apply_promotion(project, stored["candidate_id"],
                                             operation="ADD", actor="tester",
                                             expect_base="0" * 64)
            self.assertIn(caught.exception.code,
                          ("KNOWLEDGE_STALE_BASE", "KNOWLEDGE_PROMOTION_CONFLICT"))

    def test_Apply_PreservesCrlfStyle(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "AGENTS.md").write_bytes(b"# Rules\r\n")
            stored = _ready(project)
            promotionlib.apply_promotion(project, stored["candidate_id"],
                                         operation="ADD", actor="tester")
            raw = (project / "AGENTS.md").read_bytes()
            self.assertIn(b"\r\n", raw)
            self.assertNotIn(b"\n#", raw.replace(b"\r\n", b""))

    def test_Promote_FromNonReady_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = storelib.append(project, capture(
                project=str(project), agent="opencode", session="s",
                origin_type="manual", kind="PROJECT_RULE", claim="Some rule."))
            with self.assertRaises(KnowledgeError) as caught:
                promotionlib.plan_promotion(project, stored["candidate_id"],
                                            operation="ADD", actor="tester")
            self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_TRANSITION")


class AnchorOperationsTest(unittest.TestCase):
    def test_Merge_InsertsAfterAnchorLine(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n\n## Testing\n\nOld line.\n")
            stored = _ready(project, claim="Cover the new module too.")
            outcome = promotionlib.apply_promotion(
                project, stored["candidate_id"], operation="MERGE", actor="tester",
                anchor_text="## Testing")
            body = (project / "AGENTS.md").read_text(encoding="utf-8")
            self.assertLess(body.index("## Testing"), body.index("Cover the new module"))
            self.assertEqual(outcome["operation"], "MERGE")

    def test_Refine_ReplacesExactAnchor(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n\nRetry twice.\n")
            stored = _ready(project, claim="Retry three times.")
            promotionlib.apply_promotion(project, stored["candidate_id"],
                                         operation="REFINE", actor="tester",
                                         anchor_text="Retry twice.")
            body = (project / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Retry three times.", body)
            self.assertNotIn("Retry twice.", body)

    def test_Anchor_Ambiguous_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n\nSame.\n\nSame.\n")
            stored = _ready(project, claim="New.")
            with self.assertRaises(KnowledgeError) as caught:
                promotionlib.plan_promotion(project, stored["candidate_id"],
                                            operation="REFINE", actor="tester",
                                            anchor_text="Same.")
            self.assertEqual(caught.exception.code, "KNOWLEDGE_TARGET_UNSUPPORTED")

    def test_Supersede_AnnotatesAndAppends(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n\nRetry twice.\n")
            stored = _ready(project, claim="Retry three times.")
            promotionlib.apply_promotion(project, stored["candidate_id"],
                                         operation="SUPERSEDE", actor="tester",
                                         anchor_text="Retry twice.")
            body = (project / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Superseded by knowledge", body)
            self.assertIn("Retry three times.", body)

    def test_EditOps_WithoutAnchor_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _ready(project, claim="New.")
            with self.assertRaises(KnowledgeError) as caught:
                promotionlib.plan_promotion(project, stored["candidate_id"],
                                            operation="MERGE", actor="tester")
            self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")


class AdrAllocationTest(unittest.TestCase):
    def test_Adr_NumbersAllocateSequentially(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            first = _ready(project, claim="Use NATS for events.",
                           kind="ARCHITECTURE_DECISION")
            outcome = promotionlib.apply_promotion(project, first["candidate_id"],
                                                   operation="ADD", actor="tester")
            self.assertTrue(outcome["target"].endswith("0001-use-nats-for-events.md"))
            body = (project / outcome["target"]).read_text(encoding="utf-8")
            self.assertIn("Use NATS for events.", body)
            second = _ready(project, claim="Use Postgres for state.",
                            kind="ARCHITECTURE_DECISION")
            outcome2 = promotionlib.apply_promotion(project, second["candidate_id"],
                                                    operation="ADD", actor="tester")
            self.assertTrue(outcome2["target"].endswith("0002-use-postgres-for-state.md"))


class ReconcileTest(unittest.TestCase):
    def _crashed(self, project: Path) -> dict:
        """A promotion whose file write landed but whose audit did not."""

        stored = _ready(project)
        plan = promotionlib.plan_promotion(project, stored["candidate_id"],
                                           operation="ADD", actor="tester")
        dest = project / plan["target"]
        from ainative.lifecycle import state as statelib
        statelib.write_bytes_atomic(dest, plan["new_text"].encode("utf-8"))
        storelib.record_audit(project, candidate_id=stored["candidate_id"],
                              operation="PROMOTE",
                              detail={"promote_operation": "ADD",
                                      "target": plan["target"],
                                      "base_digest": plan["base_digest"],
                                      "result_digest": plan["result_digest"]},
                              actor="tester")
        return stored

    def test_Reconcile_HealsStatusAfterCrash(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = self._crashed(project)
            outcome = promotionlib.reconcile(project, stored["candidate_id"])
            self.assertEqual(outcome["state"], "healed-status")
            self.assertEqual(storelib.inspect_candidate(
                project, stored["candidate_id"])["status"], "PROMOTED")

    def test_Reconcile_DivergedNeedsHuman(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = self._crashed(project)
            _write(project, "AGENTS.md", "# Rules\n\n# Someone rewrote everything\n")
            outcome = promotionlib.reconcile(project, stored["candidate_id"])
            self.assertEqual(outcome["state"], "diverged")
            self.assertEqual(storelib.inspect_candidate(
                project, stored["candidate_id"])["status"], "READY_FOR_PROMOTION")


if __name__ == "__main__":
    unittest.main()