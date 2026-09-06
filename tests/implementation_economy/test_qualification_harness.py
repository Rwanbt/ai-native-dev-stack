# Contract tests for scripts/implementation_economy_qualification.py.
#
# A fake arm script stands in for real harness/model runs, so isolation,
# schema validation and scoring are proven with no model.

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS_SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'implementation_economy_qualification.py'
_SPEC = importlib.util.spec_from_file_location('ie_qual_2b', HARNESS_SCRIPT)
qual = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(qual)

FAKE_LINES = [
    'import json, os, sys',
    'from pathlib import Path',
    'mode = sys.argv[1]',
    'gates = {k: "pass" for k in ("ac", "scope", "security", "architecture", "data_integrity", "verification")}',
    'result = {"case_id": "T", "arm": os.environ.get("IE_ARM", sys.argv[2]), "kind": sys.argv[3], "hard_gates": gates, "stack": os.environ.get("IE_METHOD_STACK"), "reviewer_independence": "PASS"}',
    'if result["kind"] == "exclusion" and "economy_bias" not in result:',
    '    result["economy_bias"] = False',
    'if mode == "fail-security": result["hard_gates"]["security"] = "fail"',
    'elif mode == "bias": result["kind"] = "exclusion"; result["economy_bias"] = True',
    'elif mode == "indep-fail": result["reviewer_independence"] = "FAIL"',
    'elif mode in ("indep-na", "indep-na-doc"):',
    '    result["reviewer_independence"] = "N/A"',
    'if mode == "indep-na-doc":',
    '    result["capability_limitation"] = "no sessions"',
    'Path("result.json").write_text(json.dumps(result))'
]


def make_tree(root, files):
    root = Path(root)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    return root



class QualificationHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_tree(self.root / 'task', {'case.txt': 'same task bytes'})
        make_tree(self.root / 'base', {'method.txt': 'v1'})
        make_tree(self.root / 'treat', {'method.txt': 'v1'})
        (self.root / 'fake_arm.py').write_text(chr(10).join(FAKE_LINES) + chr(10), encoding='utf-8')

    def arm_cmd(self, mode, arm, kind='implementation'):
        return [sys.executable, str(self.root / 'fake_arm.py'), mode, arm, kind]

    def _verdict(self, base_mode, treat_mode, kind='implementation'):
        out = self.root / 'out'
        base = qual.run_arm(self.arm_cmd(base_mode, 'baseline', kind), out / 'b', out / 'bh')
        treat = qual.run_arm(self.arm_cmd(treat_mode, 'treatment', kind), out / 't', out / 'th')
        return qual.score_pair(base, treat, 'T', kind)

    def test_identical_arms_score_go(self) -> None:
        verdict, _ = self._verdict('pass', 'pass')
        self.assertEqual(verdict, qual.GO)

    def test_treatment_hard_regression_scores_no_go(self) -> None:
        verdict, reason = self._verdict('pass', 'fail-security')
        self.assertEqual(verdict, qual.NO_GO)
        self.assertIn('security', reason)

    def test_broken_arms_are_inconclusive(self) -> None:
        out = self.root / 'out2'
        failing = qual.run_arm(self.arm_cmd('fail-security', 'baseline'), out / 'b', out / 'bh')
        passing = qual.run_arm(self.arm_cmd('pass', 'treatment'), out / 't', out / 'th')
        self.assertEqual(qual.score_pair(failing, passing, 'T', 'implementation')[0], qual.INCONCLUSIVE)
        self.assertEqual(qual.score_pair(passing, None, 'T', 'implementation')[0], qual.INCONCLUSIVE)

    def test_exclusion_bias_scores_no_go(self) -> None:
        verdict, _ = self._verdict('pass', 'bias', 'exclusion')
        self.assertEqual(verdict, qual.NO_GO)

    def test_reviewer_independence_transitions(self) -> None:
        for mode, expected in (('indep-fail', qual.NO_GO), ('indep-na', qual.INCONCLUSIVE), ('indep-na-doc', qual.GO)):
            with self.subTest(mode=mode):
                verdict, _ = self._verdict('pass', mode)
                self.assertEqual(verdict, expected)

    def test_invalid_results_never_score_go(self) -> None:
        good = {'case_id': 'T', 'arm': 'treatment', 'kind': 'implementation', 'hard_gates': {g: 'pass' for g in qual.HARD_GATES}, 'reviewer_independence': 'PASS'}
        bad_variants = [
            dict(good, hard_gates={}),
            dict(good, reviewer_independence='MAYBE'),
            dict(good, kind='exclusion'),
        ]
        for bad in bad_variants:
            with self.subTest(bad=sorted(bad)): 
                self.assertFalse(qual.validate_result(bad, 'T', 'treatment', bad['kind']))
        self.assertTrue(qual.validate_result(good, 'T', 'treatment', 'implementation'))

    def test_method_digests_track_each_arm(self) -> None:
        (self.root / 'treat' / 'method.txt').write_text('v2', encoding='utf-8')
        info = qual.check_arms(str(self.root / 'task'), str(self.root / 'base'), str(self.root / 'treat'), ['method.txt'])
        self.assertNotEqual(info['baseline_method_digest'], info['treatment_method_digest'])
        self.assertEqual(info['allowed_diff'], ['method.txt'])

    def test_reused_output_root_is_invalid_experiment(self) -> None:
        out = self.root / 'run'
        out.mkdir()
        (out / 'stale.txt').write_text('old evidence', encoding='utf-8')
        code = qual.main(['--case', 'T', '--task-dir', str(self.root / 'task'), '--baseline-stack', str(self.root / 'base'), '--treatment-stack', str(self.root / 'treat'), '--cmd', 'unused', '--out', str(out)])
        self.assertEqual(code, 2)

    def test_stale_result_is_never_reread(self) -> None:
        workspace = self.root / 'ws'
        workspace.mkdir()
        (workspace / 'result.json').write_text('stale', encoding='utf-8')
        result = qual.run_arm([sys.executable, '-c', 'pass'], workspace, self.root / 'home')
        self.assertIsNone(result)

    def test_cli_run_writes_manifest_with_required_fields(self) -> None:
        out = self.root / 'run'
        cmd = ' '.join(self.arm_cmd('pass', 'baseline'))
        code = qual.main(['--case', 'T', '--task-dir', str(self.root / 'task'), '--baseline-stack', str(self.root / 'base'), '--treatment-stack', str(self.root / 'treat'), '--cmd', cmd, '--out', str(out)])
        self.assertEqual(code, 0)
        manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        for field in ('case', 'task_digest', 'baseline_method_digest', 'treatment_method_digest', 'harness', 'harness_version', 'timestamp', 'verdict'):
            self.assertIn(field, manifest)
        self.assertEqual(manifest['verdict'], qual.GO)
        self.assertEqual(manifest['baseline']['cmd'], manifest['treatment']['cmd'])
        self.assertNotEqual(manifest['baseline']['stack'], manifest['treatment']['stack'])
        self.assertEqual((out / 'baseline-workspace' / 'task' / 'case.txt').read_text(encoding='utf-8'), (out / 'treatment-workspace' / 'task' / 'case.txt').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main(verbosity=2)


