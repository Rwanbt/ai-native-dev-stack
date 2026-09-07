"""PR6 gates: one planner, authority/tiers/budgets/drift per B2 S1-S9."""

from __future__ import annotations

import unittest

from ainative.knowledge import planner as plannerlib
from ainative.knowledge.errors import KnowledgeError


def _source(kind: str, locator: str, scope: str = "project",
            excerpt: str = "text", **extra) -> dict:
    record = {"kind": kind, "locator": locator, "scope": scope,
              "excerpt": excerpt}
    record.update(extra)
    return record


class AuthorityTest(unittest.TestCase):
    def test_KindTable_MapsPerContract(self):
        cases = {"agents": "ENGINEERING_POLICY", "adr": "ARCHITECTURE_DECISION",
                 "source": "IMPLEMENTATION_FACT", "ai-context": "MODULE_CONSTRAINT",
                 "test": "BEHAVIOURAL_EVIDENCE", "kfp": "FAILURE_PREVENTION",
                 "research": "INFORMATIVE_RESEARCH", "session": "HISTORICAL_OBSERVATION",
                 "candidate": "UNTRUSTED", "summary": "DERIVED",
                 "mystery": "UNTRUSTED"}
        for kind, domain in cases.items():
            with self.subTest(kind=kind):
                bundle = plannerlib.plan([_source(kind, "x")])
                self.assertEqual(bundle.items[0].authority_domain, domain)

    def test_ScopePrecedence_ModuleBeforeProject(self):
        bundle = plannerlib.plan([
            _source("agents", "proj-policy", scope="project"),
            _source("ai-context", "mod", scope="module/payment")])
        self.assertEqual([item.source for item in bundle.items],
                         ["mod", "proj-policy"])

    def test_Prohibitions_AreTierA(self):
        bundle = plannerlib.plan([
            _source("note", "n", knowledge_type="PROHIBITIVE"),
            _source("agents", "p")])
        tiers = {item.source: item.tier for item in bundle.items}
        self.assertEqual(tiers["n"], "A")

    def test_Candidate_Adapter_IsUntrusted(self):
        record = {"candidate_id": "c1", "scope": {"project": "demo"},
                  "claim": "Use real DB.", "identity": {"identity_key": "k"},
                  "assertion_hash": "h"}
        adapted = plannerlib.candidate_source(record)
        bundle = plannerlib.plan([adapted])
        self.assertEqual(bundle.items[0].authority_domain, "UNTRUSTED")


class TierBudgetTest(unittest.TestCase):
    def test_TierA_NeverEvicted(self):
        policy = _source("agents", "policy", excerpt="p" * 100)
        bulk = [_source("research", f"r{i}", excerpt="x" * 100) for i in range(5)]
        bundle = plannerlib.plan(
            [policy, *bulk],
            budgets=plannerlib.Budgets(max_bytes=250, max_items=64))
        self.assertIn("policy", [item.source for item in bundle.items])
        self.assertTrue(bundle.dropped)
        self.assertTrue(all(item.tier != "A" or item.source == "policy"
                            for item in bundle.items))

    def test_Overflow_FailsVisibly(self):
        policy = _source("agents", "policy", excerpt="p" * 100)
        with self.assertRaises(KnowledgeError) as caught:
            plannerlib.plan([policy], budgets=plannerlib.Budgets(max_bytes=10))
        self.assertEqual(caught.exception.code,
                         "KNOWLEDGE_MANDATORY_CONTEXT_OVERFLOW")

    def test_EvictionOrder_LowestTierFirst(self):
        items = [_source("agents", "a", excerpt="a" * 10),
                 _source("research", "d", excerpt="d" * 10)]
        bundle = plannerlib.plan(items, budgets=plannerlib.Budgets(
            max_bytes=15, max_items=64))
        self.assertEqual([item.source for item in bundle.items], ["a"])
        self.assertEqual(bundle.dropped[0]["locator"], "d")
        self.assertIn("budget", bundle.dropped[0]["reason"])


class DriftTest(unittest.TestCase):
    def test_SameIdentity_DifferentHash_BothRetainedWithDrift(self):
        first = _source("adr", "adr3", scope="project",
                        identity_key="module/payment/retry/attempts",
                        assertion_hash="h3")
        second = _source("source", "code", scope="module/payment",
                         identity_key="module/payment/retry/attempts",
                         assertion_hash="h5")
        bundle = plannerlib.plan([first, second])
        self.assertEqual(len(bundle.items), 2)
        self.assertTrue(all(item.drift for item in bundle.items))

    def test_StaleSide_DoesNotTriggerDrift(self):
        first = _source("adr", "adr3", identity_key="k", assertion_hash="h3")
        second = _source("source", "code", identity_key="k", assertion_hash="h5",
                         freshness="STALE")
        bundle = plannerlib.plan([first, second])
        self.assertFalse(any(item.drift for item in bundle.items))

    def test_SummaryContradiction_CanonicalWins(self):
        canon = _source("ai-context", "ctx", identity_key="k",
                        assertion_hash="h1")
        summary = _source("summary", "sum", identity_key="k",
                          assertion_hash="h2")
        bundle = plannerlib.plan([summary, canon])
        self.assertEqual(bundle.items[0].source, "ctx")
        self.assertTrue(bundle.items[1].drift)


class IntentTest(unittest.TestCase):
    def test_Intent_ReordersWithinGroupOnly(self):
        first = _source("research", "r1", excerpt="alpha")
        second = _source("research", "r2", excerpt="beta")
        plain = plannerlib.plan([first, second])
        self.assertEqual([item.source for item in plain.items], ["r1", "r2"])
        steered = plannerlib.plan([first, second],
                                  intent={"emphasis": "beta"})
        self.assertEqual([item.source for item in steered.items], ["r2", "r1"])

    def test_Intent_CannotHideDrift(self):
        first = _source("adr", "adr3", identity_key="k", assertion_hash="h3")
        second = _source("source", "code", identity_key="k", assertion_hash="h5")
        bundle = plannerlib.plan([first, second], intent={"emphasis": "code"})
        self.assertEqual(len(bundle.items), 2)
        self.assertTrue(all(item.drift for item in bundle.items))

    def test_Intent_CannotDropTierA(self):
        bundle = plannerlib.plan(
            [_source("research", "r"), _source("agents", "p")],
            intent={"emphasis": "research"},
            budgets=plannerlib.Budgets(max_bytes=10**6, max_items=1))
        self.assertEqual(bundle.items[0].source, "p")

    def test_NaturalLanguageOnly_RequestHasNoFilterPower(self):
        bundle = plannerlib.plan(
            [_source("agents", "p"), _source("source", "c")],
            intent={"emphasis": "show me only implementation"})
        self.assertEqual(len(bundle.items), 2)


class ScopeTest(unittest.TestCase):
    def test_UnknownScope_Dropped(self):
        bundle = plannerlib.plan([_source("agents", "x", scope="???")])
        self.assertEqual(bundle.items, [])
        self.assertEqual(bundle.dropped[0]["reason"], "scope inapplicable")

    def test_UnconfiguredShared_Dropped(self):
        bundle = plannerlib.plan(
            [_source("research", "g", scope="global/shared")])
        self.assertEqual(bundle.items, [])

    def test_ConfiguredShared_Allowed(self):
        bundle = plannerlib.plan(
            [_source("research", "g", scope="global/shared")],
            shared_roots=frozenset({"shared"}), allow_shared=True)
        self.assertEqual(len(bundle.items), 1)

    def test_Focus_NarrowsModule(self):
        bundle = plannerlib.plan(
            [_source("ai-context", "pay", scope="module/payment"),
             _source("ai-context", "bill", scope="module/billing")],
            focus=["module/payment/checkout"])
        self.assertEqual([item.source for item in bundle.items], ["pay"])


class DeterminismTest(unittest.TestCase):
    def test_ShuffledInput_SameOutput(self):
        items = [_source("research", f"r{i}", excerpt=f"text {i}") for i in range(6)]
        first = plannerlib.plan(list(items))
        second = plannerlib.plan(list(reversed(items)))
        self.assertEqual([item.source for item in first.items],
                         [item.source for item in second.items])
        self.assertEqual(first.total_bytes, second.total_bytes)


if __name__ == "__main__":
    unittest.main()
