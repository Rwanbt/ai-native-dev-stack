import tempfile, unittest
from pathlib import Path
from ainative.multivault.authority_store import AuthorityStore
class AuthorityStoreTests(unittest.TestCase):
 def test_store_is_empty_until_operator_writes_binding(self):
  with tempfile.TemporaryDirectory() as directory:
   store=AuthorityStore(Path(directory)/"authority.json"); self.assertIsNone(store.binding("company-a")); store.replace({"company-a":{"vault":"v","checkout":"c"}}); self.assertEqual("v",store.binding("company-a")["vault"])
