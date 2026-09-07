"""PR2: root-specific identity grammar (B1 S6-S8)."""

from __future__ import annotations

import unittest

from ainative.knowledge import identity as identitylib
from ainative.knowledge.errors import KnowledgeError

MODULES = frozenset({"payment", "vault"})
SLUG = "ai-native-dev-stack"


def _parse(key: str, **overrides):
    options = {"modules": MODULES, "project_slug": SLUG}
    options.update(overrides)
    return identitylib.parse_identity(key, **options)


class IdentityTest(unittest.TestCase):
    def test_Module_KnownId_ParsesWithScope(self):
        identity = _parse("module/payment/retry/attempts")
        self.assertEqual(identity.scope, "module/payment")
        self.assertEqual(identity.root, "module")

    def test_Module_UnknownId_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            _parse("module/nope/retry/attempts")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_IDENTITY_KEY_INVALID")

    def test_Project_SlugMustMatchExactly(self):
        identity = _parse("project/ai-native-dev-stack/workflow/review")
        self.assertEqual(identity.scope, "project/ai-native-dev-stack")
        with self.assertRaises(KnowledgeError):
            _parse("project/other/workflow/review")

    def test_Repo_AreaRegistry(self):
        identity = _parse("repo/testing/policy/retry")
        self.assertEqual(identity.scope, "repo")
        with self.assertRaises(KnowledgeError):
            _parse("repo/billing/policy/retry")

    def test_Global_NeedsConfiguredRoot(self):
        with self.assertRaises(KnowledgeError):
            _parse("global/shared/policy/retry")
        identity = _parse("global/shared/policy/retry",
                          shared_roots=frozenset({"shared"}))
        self.assertEqual(identity.scope, "global")

    def test_GenericRoot_Forbidden(self):
        with self.assertRaises(KnowledgeError):
            _parse("root/payment/retry/attempts")

    def test_Vocabulary_OutOfVocab_Refused(self):
        with self.assertRaises(KnowledgeError):
            _parse("module/payment/retry/flibbertigibbet")

    def test_Shape_IllegalSegments_Refused(self):
        for bad in ("module/payment/Retry/attempts", "module/payment//attempts",
                    "module/payment/retry/", "tooshort", "a/b",
                    "module/payment/" + "x" * 65 + "/retry"):
            with self.subTest(key=bad):
                with self.assertRaises(KnowledgeError):
                    _parse(bad)

    def test_MinimumShape_FourParts(self):
        with self.assertRaises(KnowledgeError) as caught:
            _parse("module/payment/retry")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_IDENTITY_KEY_INVALID")

    def test_ComposedSegment_ResolvesAtomWise(self):
        identity = _parse("module/payment/retry/max-attempts")
        self.assertEqual(identity.scope, "module/payment")
        with self.assertRaises(KnowledgeError):
            _parse("module/payment/retry/max-flibbertigibbet")

    def test_Screen_DetectsCredentialClasses(self):
        self.assertEqual(identitylib.screen_secret("api_key = abc"), "credential")
        self.assertEqual(identitylib.screen_secret("use bearer token"), "credential")
        self.assertEqual(
            identitylib.screen_secret("-----BEGIN PRIVATE KEY-----"),
            "private-key")
        self.assertIsNone(identitylib.screen_secret("retry attempts"))
        self.assertIsNone(identitylib.screen_secret(None))

    def test_SecretShapedSegment_Refused(self):
        # "bearer" fails vocabulary first: with a bounded taxonomy the
        # screen is defense in depth here, proven directly above and on
        # free-text fields (tombstone reason). Either refusal blocks it.
        with self.assertRaises(KnowledgeError) as caught:
            _parse("module/payment/rule/bearer")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_IDENTITY_KEY_INVALID")

    def test_Attest_ExplicitActor(self):
        identity = _parse("module/payment/retry/attempts")
        attested = identitylib.attest(identity, actor="lead")
        self.assertEqual(attested["confirmed_by"], "lead")
        with self.assertRaises(KnowledgeError):
            identitylib.attest(identity, actor="")


if __name__ == "__main__":
    unittest.main()
