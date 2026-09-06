# Contract tests for scripts/implementation_economy_qualification.py.
#
# A fake arm script stands in for real harness/model runs, so every
# isolation and scoring rule is proven deterministically with no model.

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
    'import json, sys',
    'from pathlib import Path',
    'mode = sys.argv[1]',
    'gates = {k: "pass" for k in ("ac", "scope", "security", "architecture", "data_integrity", "verification")}',
    'result = {"case_id": "T", "arm": sys.argv[2], "kind": sys.argv[3], "hard_gates": gates, "metrics": {}}',
    'if mode == "fail-security":',
    '    result["hard_gates"]["security"] = "fail"',
    'elif mode == "bias":',
    '    result["kind"] = "exclusion"',
    '    result["economy_bias"] = True',
    'elif mode == "indep-fail":',
    '    result["reviewer_independence"] = "FAIL"',
    'elif mode in ("indep-na", "indep-na-doc"):',
    '    result["reviewer_independence"] = "N/A"',
    'if mode == "indep-na-doc":',
    '    result["capability_limitation"] = "no sessions"',
    'Path("result.json").write_text(json.dumps(result))',
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

    def test_identical_arms_score_go(self) -> None:
        info = qual.check_arms(str(self.root / 'task'), str(self.root / 'base'), str(self.root / 'treat'), [])
        self.assertEqual(info['allowed_diff'], [])
        out = self.root / 'out'
        base = qual.run_arm(self.arm_cmd('pass', 'baseline'), out / 'b-ws', out / 'b-home')
        treat = qual.run_arm(self.arm_cmd('pass', 'treatment'), out / 't-ws', out / 't-home')
        verdict, _ = qual.score_pair(base, treat)
        self.assertEqual(verdict, qual.GO)
        first, _ = qual.tree_digest(self.root / 'task')
        second, _ = qual.tree_digest(self.root / 'task')
        self.assertEqual(first, second)

    def test_non_allowlisted_method_difference_is_invalid_experiment(self) -> None:
        (self.root / 'treat' / 'method.txt').write_text('v2', encoding='utf-8')
        with self.assertRaises(qual.QualificationError):
            qual.check_arms(str(self.root / 'task'), str(self.root / 'base'), str(self.root / 'treat'), [])

    def test_allowlisted_method_difference_passes(self) -> None:
        (self.root / 'treat' / 'method.txt').write_text('v2', encoding='utf-8')
        info = qual.check_arms(str(self.root / 'task'), str(self.root / 'base'), str(self.root / 'treat'), ['method.txt'])
        self.assertEqual(info['allowed_diff'], ['method.txt'])

    def test_treatment_hard_regression_scores_no_go(self) -> None:
        out = self.root / 'out'
        base = qual.run_arm(self.arm_cmd('pass', 'baseline'), out / 'b', out / 'bh')
        treat = qual.run_arm(self.arm_cmd('fail-security', 'treatment'), out / 't', out / 'th')
        verdict, reason = qual.score_pair(base, treat)
        self.assertEqual(verdict, qual.NO_GO)
        self.assertIn('security', reason)

    def test_baseline_failure_is_inconclusive(self) -> None:
        out = self.root / 'out'
        base = qual.run_arm(self.arm_cmd('fail-security', 'baseline'), out / 'b', out / 'bh')
        treat = qual.run_arm(self.arm_cmd('pass', 'treatment'), out / 't', out / 'th')
        verdict, _ = qual.score_pair(base, treat)
        self.assertEqual(verdict, qual.INCONCLUSIVE)

    def test_missing_result_is_inconclusive(self) -> None:
        out = self.root / 'out'
        base = qual.run_arm(self.arm_cmd('pass', 'baseline'), out / 'b', out / 'bh')
        verdict, _ = qual.score_pair(base, None)
        self.assertEqual(verdict, qual.INCONCLUSIVE)

    def test_exclusion_bias_scores_no_go(self) -> None:
        out = self.root / 'out'
        base = qual.run_arm(self.arm_cmd('pass', 'baseline', 'exclusion'), out / 'b', out / 'bh')
        treat = qual.run_arm(self.arm_cmd('bias', 'treatment', 'exclusion'), out / 't', out / 'th')
        verdict, _ = qual.score_pair(base, treat)
        self.assertEqual(verdict, qual.NO_GO)

    def test_undocumented_na_independence_is_inconclusive(self) -> None:
        out = self.root / 'out'
        base = qual.run_arm(self.arm_cmd('pass', 'baseline'), out / 'b', out / 'bh')
        treat = qual.run_arm(self.arm_cmd('indep-na', 'treatment'), out / 't', out / 'th')
        verdict, _ = qual.score_pair(base, treat)
        self.assertEqual(verdict, qual.INCONCLUSIVE)

    def test_documented_na_independence_can_pass(self) -> None:
        out = self.root / 'out'
        base = qual.run_arm(self.arm_cmd('pass', 'baseline'), out / 'b', out / 'bh')
        treat = qual.run_arm(self.arm_cmd('indep-na-doc', 'treatment'), out / 't', out / 'th')
        verdict, _ = qual.score_pair(base, treat)
        self.assertEqual(verdict, qual.GO)

    def test_cli_run_writes_manifest_with_required_fields(self) -> None:
        out = self.root / 'run'
        base_cmd = ' '.join(self.arm_cmd('pass', 'baseline'))
        treat_cmd = ' '.join(self.arm_cmd('pass', 'treatment'))
        code = qual.main(['--case', 'T', '--task-dir', str(self.root / 'task'), '--baseline-stack', str(self.root / 'base'), '--treatment-stack', str(self.root / 'treat'), '--baseline-cmd', base_cmd, '--treatment-cmd', treat_cmd, '--out', str(out)])
        self.assertEqual(code, 0)
        manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        for field in ('case', 'task_digest', 'method_digest', 'harness', 'harness_version', 'timestamp', 'verdict'):
            self.assertIn(field, manifest)
        self.assertEqual(manifest['verdict'], qual.GO)


if __name__ == '__main__':
    unittest.main(verbosity=2)

