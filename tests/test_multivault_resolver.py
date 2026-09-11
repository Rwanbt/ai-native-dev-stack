import tempfile, unittest
from pathlib import Path
from ainative.multivault.authority_store import AuthorityStore
from ainative.multivault.binding import WorkspaceDeclaration
from ainative.multivault.resolver import resolve
from ainative.multivault.schema import SecurityClassification


class ResolverTests(unittest.TestCase):
 def test_unbound_context_is_descriptive_but_not_authorized(self):
  with tempfile.TemporaryDirectory() as directory:
   result=resolve(WorkspaceDeclaration("a","v","c"),AuthorityStore(Path(directory)/"a.json"))
  self.assertEqual("a",result.security_domain_id); self.assertFalse(result.authorized); self.assertIsNone(result.classification)

 def test_authorized_context_exposes_only_the_trusted_classification(self):
  with tempfile.TemporaryDirectory() as directory:
   store=AuthorityStore(Path(directory)/"a.json"); store.replace({"a":{"vault":"v","checkout":"c","classification":"TEAM"}})
   result=resolve(WorkspaceDeclaration("a","v","c",SecurityClassification.PERSONAL),store)
  self.assertTrue(result.authorized); self.assertEqual(SecurityClassification.TEAM,result.classification)

 def test_denied_context_never_exposes_a_classification(self):
  with tempfile.TemporaryDirectory() as directory:
   store=AuthorityStore(Path(directory)/"a.json"); store.replace({"a":{"vault":"v","checkout":"c","classification":"PERSONAL"}})
   result=resolve(WorkspaceDeclaration("a","v","c",SecurityClassification.CRITICAL),store)
  self.assertFalse(result.authorized); self.assertIsNone(result.classification)