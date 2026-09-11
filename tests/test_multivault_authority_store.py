import tempfile, unittest
from pathlib import Path
from ainative.multivault.authority_store import AuthorityStore, AuthorityStoreCorruptError


class AuthorityStoreTests(unittest.TestCase):
 def test_store_is_empty_until_operator_writes_binding(self):
  with tempfile.TemporaryDirectory() as directory:
   store=AuthorityStore(Path(directory)/"authority.json"); self.assertIsNone(store.binding("company-a")); store.replace({"company-a":{"vault":"v","checkout":"c"}}); self.assertEqual("v",store.binding("company-a")["vault"])

 def test_corrupt_store_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   store=AuthorityStore(Path(directory)/"authority.json"); store.path.write_text("{not json", encoding="utf-8")
   with self.assertRaises(AuthorityStoreCorruptError): store.bindings()

 def test_unsupported_schema_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   store=AuthorityStore(Path(directory)/"authority.json"); store.path.write_text('{"schema_version":99,"bindings":{}}', encoding="utf-8")
   with self.assertRaises(AuthorityStoreCorruptError): store.bindings()

 def test_replace_backs_up_previous_generation_and_recovers(self):
  with tempfile.TemporaryDirectory() as directory:
   store=AuthorityStore(Path(directory)/"authority.json")
   store.replace({"a":{"vault":"v1","checkout":"c1"}})
   store.replace({"a":{"vault":"v2","checkout":"c2"}})
   self.assertEqual("v2",store.binding("a")["vault"])
   store.path.write_text("garbage", encoding="utf-8")
   with self.assertRaises(AuthorityStoreCorruptError): store.bindings()
   self.assertTrue(store.restore_from_backup())
   self.assertEqual("v1",store.binding("a")["vault"])