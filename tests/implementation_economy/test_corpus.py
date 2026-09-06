# Non-vacuity and schema contract for the deterministic IE corpus.
#
# A green run with zero discovered cases is a failure, enforced by
# test_discovered_count_matches_expected against EXPECTED_CORPUS_CASE_COUNT.

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location('ie_corpus_2a', PKG / 'corpus.py')
corpus = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(corpus)

MANDATORY_IDS = ('WORK_CONTRACT_SCOPE_DRIFT', 'OWNERSHIP_FIRST_CHANGES_BOUND_IMPLEMENTATION_PATH', 'DYNAMIC_PLUGIN_ENTRYPOINT', 'CLI_ENTRYPOINT_BY_STRING', 'EVENT_CALLBACK_WITH_NO_STATIC_CALLER', 'PUBLIC_API_WITH_NO_INTERNAL_CALLERS', 'FFI_EXPORTED_SYMBOL', 'WRAPPER_THAT_OWNS_TRACING', 'WRAPPER_THAT_OWNS_AUTH', 'SHORTER_STDLIB_SOLUTION_VIOLATES_PERFORMANCE_BUDGET', 'ATOMIC_WRITE_REPLACED_BY_UNSAFE_DIRECT_WRITE', 'VALID_SINGLE_CONSUMER_ADAPTER', 'OWNERSHIP_AMBIGUITY_MUST_NOT_DUPLICATE_POLICY', 'MECHANICALLY_DEAD_BUT_OUT_OF_SCOPE')


class CorpusContract(unittest.TestCase):
    def test_discovered_count_matches_expected(self) -> None:
        cases = corpus.load_corpus()
        found = len(cases)
        print('Implementation Economy corpus: ' + str(found) + '/' + str(corpus.EXPECTED_CORPUS_CASE_COUNT) + ' cases discovered')
        self.assertGreater(corpus.EXPECTED_CORPUS_CASE_COUNT, 0)
        self.assertEqual(found, corpus.EXPECTED_CORPUS_CASE_COUNT)

    def test_every_family_represented(self) -> None:
        families = {case['family'] for case in corpus.load_corpus()}
        for family in corpus.VALID_FAMILIES:
            with self.subTest(family=family):
                self.assertIn(family, families)

    def test_mandatory_case_ids_present(self) -> None:
        ids = {case['id'] for case in corpus.load_corpus()}
        for case_id in MANDATORY_IDS:
            with self.subTest(case=case_id):
                self.assertIn(case_id, ids)


    def _write_case(self, directory, name, payload):
        path = Path(directory) / name
        if isinstance(payload, dict):
            path.write_text(json.dumps(payload), encoding='utf-8')
        else:
            path.write_text(payload, encoding='utf-8')
        return path

    def _valid_payload(self):
        return {'id': 'PROBE', 'family': 'SCOPE', 'title': 'probe', 'task': 'probe task', 'acceptance_criteria': ['probe criterion'], 'expected': {'probe': True}}

    def test_schema_rejects_invalid_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._valid_payload()
            payload['family'] = 'NOPE'
            self._write_case(tmp, 'bad.json', payload)
            with self.assertRaises(corpus.CorpusError):
                corpus.load_corpus(tmp)

    def test_schema_rejects_empty_acceptance_criteria(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._valid_payload()
            payload['acceptance_criteria'] = []
            self._write_case(tmp, 'bad.json', payload)
            with self.assertRaises(corpus.CorpusError):
                corpus.load_corpus(tmp)

    def test_schema_rejects_missing_required_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._valid_payload()
            del payload['expected']
            self._write_case(tmp, 'bad.json', payload)
            with self.assertRaises(corpus.CorpusError):
                corpus.load_corpus(tmp)

    def test_schema_rejects_unknown_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._valid_payload()
            payload['surprise'] = 1
            self._write_case(tmp, 'bad.json', payload)
            with self.assertRaises(corpus.CorpusError):
                corpus.load_corpus(tmp)

    def test_duplicate_ids_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_case(tmp, 'a.json', self._valid_payload())
            self._write_case(tmp, 'b.json', self._valid_payload())
            with self.assertRaises(corpus.CorpusError):
                corpus.load_corpus(tmp)

    def test_schema_rejects_string_for_requires_persistent_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._valid_payload()
            payload['requires_persistent_session'] = 'false'
            self._write_case(tmp, 'bad.json', payload)
            with self.assertRaises(corpus.CorpusError):
                corpus.load_corpus(tmp)

    def test_schema_rejects_bool_for_hard_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._valid_payload()
            payload['hard_boundaries'] = True
            self._write_case(tmp, 'bad.json', payload)
            with self.assertRaises(corpus.CorpusError):
                corpus.load_corpus(tmp)

    def test_schema_rejects_string_for_excluded_activities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._valid_payload()
            payload['excluded_activities'] = 'security_review'
            self._write_case(tmp, 'bad.json', payload)
            with self.assertRaises(corpus.CorpusError):
                corpus.load_corpus(tmp)

    def test_schema_rejects_bool_for_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._valid_payload()
            payload['transition'] = False
            self._write_case(tmp, 'bad.json', payload)
            with self.assertRaises(corpus.CorpusError):
                corpus.load_corpus(tmp)


    def test_empty_directory_cannot_satisfy_expected_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(corpus.load_corpus(tmp), [])
            self.assertNotEqual(0, corpus.EXPECTED_CORPUS_CASE_COUNT)


if __name__ == '__main__':
    unittest.main(verbosity=2)

