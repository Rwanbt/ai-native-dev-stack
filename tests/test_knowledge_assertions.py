"""PR2: assertion hashing, tombstones, envelope fail-closed (B1 S9/S10/S14)."""

from __future__ import annotations

import unittest

from ainative.knowledge import assertions as assertionslib
from ainative.knowledge import envelope as envelopelib
from ainative.knowledge import identity as identitylib
from ainative.knowledge.errors import KnowledgeError


def _identity():
    return identitylib.parse_identity(
        "module/payment/retry/attempts", modules=frozenset({"payment"}),
        project_slug="ai-native-dev-stack")


class AssertionsTest(unittest.TestCase):
    def test_Hash_DeterministicAcrossKeyOrder(self):
        first = assertionslib.assertion_hash(_identity(), "module/payment", 3)
        second = assertionslib.assertion_hash(_identity(), "module/payment",
                                              {"value": 3, "type": "integer"})
        self.assertEqual(first["assertion_hash"], second["assertion_hash"])
        self.assertEqual(first["hash_algorithm"], "sha256")
        self.assertEqual(first["assertion_normalization_version"], 1)

    def test_Hash_DomainSeparated(self):
        digest = assertionslib.assertion_hash(_identity(), "module/payment", 3)
        import hashlib, json
        raw = hashlib.sha256(json.dumps(
            {"identity_key": "x"}, sort_keys=True).encode()).hexdigest()
        self.assertNotEqual(digest["assertion_hash"], raw)

    def test_Hash_ChangesWithValue(self):
        base = assertionslib.assertion_hash(_identity(), "module/payment", 3)
        other = assertionslib.assertion_hash(_identity(), "module/payment", 5)
        self.assertNotEqual(base["assertion_hash"], other["assertion_hash"])

    def test_Value_Unsupported_Refused(self):
        with self.assertRaises(KnowledgeError):
            assertionslib.assertion_hash(_identity(), "module/payment", 3.5)

    def test_Tombstone_SecretReason_Refused(self):
        digest = assertionslib.assertion_hash(_identity(), "module/payment", 3)
        with self.assertRaises(KnowledgeError) as caught:
            assertionslib.tombstone(digest["assertion_hash"],
                                    reason="leaked api_key = abc",
                                    actor="lead")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REFUSED")

    def test_Tombstone_HoldsNoRawText(self):
        digest = assertionslib.assertion_hash(_identity(), "module/payment", 3)
        marker = assertionslib.tombstone(digest["assertion_hash"],
                                         reason="superseded by ADR-99",
                                         actor="lead")
        blob = str(marker)
        self.assertNotIn("retry", blob)
        self.assertNotIn("payment", blob.replace("superseded", ""))
        self.assertEqual(marker["assertion_hash"], digest["assertion_hash"])


class EnvelopeTest(unittest.TestCase):
    def test_WrapUnwrap_RoundTrips(self):
        record = envelopelib.wrap("tombstone", "tb_1", {"h": "abc"})
        self.assertEqual(envelopelib.unwrap(record)["record_id"], "tb_1")

    def test_FutureSchema_FailsClosed(self):
        record = {"schema_version": 99, "record_type": "candidate",
                  "record_id": "x", "payload": {}}
        with self.assertRaises(KnowledgeError) as caught:
            envelopelib.unwrap(record)
        self.assertEqual(caught.exception.code, "KNOWLEDGE_SCHEMA_UNKNOWN")

    def test_UnknownType_Refused(self):
        with self.assertRaises(KnowledgeError):
            envelopelib.wrap("starship", "x", {})

    def test_Unwrap_MirrorsWrapStrictness(self):
        with self.assertRaises(KnowledgeError):
            envelopelib.unwrap({"schema_version": 1, "record_type": "candidate"})
        with self.assertRaises(KnowledgeError):
            envelopelib.unwrap({"schema_version": 1, "record_type": "candidate",
                                "record_id": "x", "payload": [1, 2]})


if __name__ == "__main__":
    unittest.main()
