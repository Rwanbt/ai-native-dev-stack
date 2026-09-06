# Deterministic stdlib loader for the Implementation Economy qualification corpus.
#
# No model, no network, no third-party dependency. A green run with zero
# discovered cases is a failure: see EXPECTED_CORPUS_CASE_COUNT.
#
# Explicit invocation:
#   python -m unittest discover -s tests/implementation_economy -p "test_*.py"

from __future__ import annotations

import json
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent / 'fixtures'

EXPECTED_CORPUS_CASE_COUNT = 6

VALID_FAMILIES = ('OVERBUILD', 'UNDERBUILD', 'OWNERSHIP', 'NOVELTY', 'SCOPE', 'EXCLUSION')

REQUIRED_FIELDS = ('id', 'family', 'title', 'task', 'acceptance_criteria', 'expected')

OPTIONAL_FIELDS = ('hard_boundaries', 'adversarial_prompt', 'transition', 'requires_persistent_session', 'excluded_activities')


class CorpusError(ValueError):
    pass


def _require_non_empty_str(case_id, field, value):
    if not isinstance(value, str) or not value.strip():
        raise CorpusError(case_id + ': ' + field + ' must be a non-empty string')




def _require_list_of_non_empty_str(case_id, field, value):
    if not isinstance(value, list) or not value:
        raise CorpusError(case_id + ': ' + field + ' must be a non-empty list of strings')
    for item in value:
        _require_non_empty_str(case_id, field + ' item', item)

def load_case(path):
    # Load and schema-validate one fixture file.
    try:
        raw = Path(path).read_text(encoding='utf-8')
    except OSError as exc:
        raise CorpusError(str(path) + ': unreadable fixture') from exc
    try:
        case = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CorpusError(str(path) + ': invalid JSON') from exc
    if not isinstance(case, dict):
        raise CorpusError(str(path) + ': fixture must be a JSON object')
    unknown = sorted(set(case) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS))
    if unknown:
        raise CorpusError(str(case.get('id', path)) + ': unknown fields ' + ','.join(unknown))
    for field in REQUIRED_FIELDS:
        if field not in case:
            raise CorpusError(str(case.get('id', path)) + ': missing field ' + field)
    case_id = case['id']
    for field in ('id', 'family', 'title', 'task'):
        _require_non_empty_str(str(case_id), field, case[field])
    if case['family'] not in VALID_FAMILIES:
        raise CorpusError(str(case_id) + ': invalid family ' + str(case['family']))
    criteria = case['acceptance_criteria']
    if not isinstance(criteria, list) or not criteria:
        raise CorpusError(str(case_id) + ': acceptance_criteria must be a non-empty list')
    for criterion in criteria:
        _require_non_empty_str(str(case_id), 'acceptance_criteria item', criterion)
    if not isinstance(case['expected'], dict) or not case['expected']:
        raise CorpusError(str(case_id) + ': expected must be a non-empty object')
    if 'hard_boundaries' in case:
        _require_list_of_non_empty_str(str(case_id), 'hard_boundaries', case['hard_boundaries'])
    if 'excluded_activities' in case:
        _require_list_of_non_empty_str(str(case_id), 'excluded_activities', case['excluded_activities'])
    for field in ('adversarial_prompt', 'transition'):
        if field in case:
            _require_non_empty_str(str(case_id), field, case[field])
    if 'requires_persistent_session' in case and not isinstance(case['requires_persistent_session'], bool):
        raise CorpusError(str(case_id) + ': requires_persistent_session must be a boolean')
    return case


def load_corpus(directory=CORPUS_DIR):
    # Load every fixture, sorted by filename. Duplicate ids fail.
    files = sorted(Path(directory).glob('*.json'))
    cases = [load_case(path) for path in files]
    ids = [case['id'] for case in cases]
    if len(set(ids)) != len(ids):
        raise CorpusError('duplicate case ids in ' + str(directory))
    return cases

