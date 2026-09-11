import tempfile, unittest
from pathlib import Path
from ainative.multivault.authority_store import AuthorityStore
from ainative.multivault.binding import WorkspaceDeclaration, admit
from ainative.multivault.schema import SecurityClassification


def store_with(directory: str, binding: dict) -> AuthorityStore:
    store = AuthorityStore(Path(directory) / "a.json")
    store.replace({"a": binding})
    return store


class BindingTests(unittest.TestCase):
 def test_declaration_cannot_expand_operator_binding(self):
  with tempfile.TemporaryDirectory() as directory:
   store=store_with(directory, {"vault":"v","checkout":"c"})
   self.assertTrue(admit(WorkspaceDeclaration("a","v","c"),store)); self.assertFalse(admit(WorkspaceDeclaration("a","foreign","c"),store))

 def test_repository_cannot_raise_the_trusted_classification(self):
  with tempfile.TemporaryDirectory() as directory:
   store=store_with(directory, {"vault":"v","checkout":"c","classification":"PERSONAL"})
   self.assertTrue(admit(WorkspaceDeclaration("a","v","c",SecurityClassification.PERSONAL),store))
   self.assertFalse(admit(WorkspaceDeclaration("a","v","c",SecurityClassification.CRITICAL),store))

 def test_repository_cannot_expand_context_roots(self):
  with tempfile.TemporaryDirectory() as directory:
   store=store_with(directory, {"vault":"v","checkout":"c","roots":["repo-a"]})
   self.assertTrue(admit(WorkspaceDeclaration("a","v","c",requested_roots=("repo-a",)),store))
   self.assertFalse(admit(WorkspaceDeclaration("a","v","c",requested_roots=("repo-a","repo-b")),store))

 def test_unknown_trusted_classification_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   store=store_with(directory, {"vault":"v","checkout":"c","classification":"SECRET"})
   self.assertFalse(admit(WorkspaceDeclaration("a","v","c"),store))