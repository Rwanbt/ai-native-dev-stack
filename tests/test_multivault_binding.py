import tempfile, unittest
from pathlib import Path
from ainative.multivault.authority_store import AuthorityStore
from ainative.multivault.binding import WorkspaceDeclaration, admit
class BindingTests(unittest.TestCase):
 def test_declaration_cannot_expand_operator_binding(self):
  with tempfile.TemporaryDirectory() as directory:
   store=AuthorityStore(Path(directory)/"a.json"); store.replace({"a":{"vault":"v","checkout":"c"}})
   self.assertTrue(admit(WorkspaceDeclaration("a","v","c"),store)); self.assertFalse(admit(WorkspaceDeclaration("a","foreign","c"),store))
