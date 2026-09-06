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

SEED_IDS = ('OVERBUILD_REUSE_EXISTING_HELPER', 'UNDERBUILD_AUTH_MUST_REMAIN', 'OWNERSHIP_SHARED_POLICY_KEEPS_CANONICAL_OWNER', 'NOVELTY_UNJUSTIFIED_DEPENDENCY', 'SCOPE_ADJACENT_DEBT_STAYS_OUT', 'EXCLUSION_ARCHITECTURE_REVIEW_STAYS_UNBIASED')


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

    def test_mandatory_seed_ids_present(self) -> None:
        ids = {case['id'] for case in corpus.load_corpus()}
        for case_id in SEED_IDS:
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

    def test_empty_directory_cannot_satisfy_expected_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(corpus.load_corpus(tmp), [])
            self.assertNotEqual(0, corpus.EXPECTED_CORPUS_CASE_COUNT)


if __name__ == '__main__':
    unittest.main(verbosity=2)

