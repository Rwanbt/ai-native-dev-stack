import tempfile, unittest
from pathlib import Path
from ainative.multivault.authority_store import AuthorityStore
from ainative.multivault.binding import WorkspaceDeclaration
from ainative.multivault.resolver import resolve
class ResolverTests(unittest.TestCase):
 def test_unbound_context_is_descriptive_but_not_authorized(self):
  with tempfile.TemporaryDirectory() as directory:
   result=resolve(WorkspaceDeclaration("a","v","c"),AuthorityStore(Path(directory)/"a.json"))
  self.assertEqual("a",result.security_domain_id); self.assertFalse(result.authorized)
