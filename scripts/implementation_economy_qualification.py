#!/usr/bin/env python3
# Paired-arm behavioral qualification: isolated arms, task equivalence,
# allowlisted methodology delta, SHA-256 digests, hard-gate-first scoring.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HARNESS = 'implementation_economy_qualification'
HARNESS_VERSION = '1.0.0'

HARD_GATES = ('ac', 'scope', 'security', 'architecture', 'data_integrity', 'verification')

GO = 'GO'
NO_GO = 'NO-GO'
INVALID_EXPERIMENT = 'INVALID_EXPERIMENT'
INCONCLUSIVE = 'INCONCLUSIVE'


class QualificationError(Exception):
    pass


def file_hashes(root):
    # Relative path to SHA-256 for every file. Missing root fails closed.
    root = Path(root)
    if not root.is_dir():
        raise QualificationError('missing tree: ' + str(root))
    out = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def digest_names(hashes):
    # Content-addressed digest of a file inventory.
    digest = hashlib.sha256()
    for name in sorted(hashes):
        digest.update(name.encode('utf-8'))
        digest.update(hashes[name].encode('utf-8'))
    digest.update(str(len(hashes)).encode('utf-8'))
    return digest.hexdigest()


def check_arms(task_dir, baseline_stack, treatment_stack, allowlist):
    # Fail closed before any model call: identical tasks, allowlisted delta.
    task_digest = digest_names(file_hashes(task_dir))
    base_files = file_hashes(baseline_stack)
    treat_files = file_hashes(treatment_stack)
    differing = sorted(n for n in set(base_files) | set(treat_files) if base_files.get(n) != treat_files.get(n))
    allowed = [d for d in differing if any(d == a or (a.endswith('*') and d.startswith(a[:-1])) for a in allowlist)]
    if len(allowed) != len(differing):
        raise QualificationError('non-allowlisted methodology difference: ' + str([d for d in differing if d not in allowed]))
    return {'task_digest': task_digest, 'baseline_method_digest': digest_names(base_files), 'treatment_method_digest': digest_names(treat_files), 'allowed_diff': allowed}


def run_arm(command, workspace, home, extra_env=None, timeout_s=600):
    # One process: own workspace, HOME (+USERPROFILE on Windows), extra env.
    # A stale result.json is removed first so it can never be re-read.
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    result_file = workspace / 'result.json'
    if result_file.is_file():
        result_file.unlink()
    env = dict(os.environ)
    env['HOME'] = str(home)
    if os.name == 'nt':
        env['USERPROFILE'] = str(home)
    env.update(extra_env or {})
    completed = subprocess.run(command, cwd=str(workspace), env=env, capture_output=True, text=True, timeout=timeout_s)
    if completed.returncode != 0 or not result_file.is_file():
        return None
    try:
        result = json.loads(result_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return result if isinstance(result, dict) else None


def validate_result(result, case_id, arm, kind):
    # Fail-closed evidence contract: every field explicit, no silent defaults.
    if not isinstance(result, dict):
        return False
    if result.get('case_id') != case_id or result.get('arm') != arm:
        return False
    if result.get('kind') != kind:
        return False
    gates = result.get('hard_gates')
    if not isinstance(gates, dict):
        return False
    if any(gates.get(gate) not in ('pass', 'fail') for gate in HARD_GATES):
        return False
    if result.get('reviewer_independence') not in ('PASS', 'FAIL', 'N/A'):
        return False
    if kind == 'exclusion' and not isinstance(result.get('economy_bias'), bool):
        return False
    return True


def score_pair(baseline, treatment, case_id, kind):
    # Hard gates first. Invalid output or a broken baseline is INCONCLUSIVE.
    if not validate_result(baseline, case_id, 'baseline', kind):
        return INCONCLUSIVE, 'invalid baseline result'
    if not validate_result(treatment, case_id, 'treatment', kind):
        return INCONCLUSIVE, 'invalid treatment result'
    base_indep = baseline['reviewer_independence']
    if base_indep == 'FAIL' or (base_indep == 'N/A' and not baseline.get('capability_limitation')):
        return INCONCLUSIVE, 'baseline reviewer independence not established'
    base_gates = baseline['hard_gates']
    if any(base_gates[gate] == 'fail' for gate in HARD_GATES):
        return INCONCLUSIVE, 'baseline gate failed'
    treat_gates = treatment['hard_gates']
    failed = [gate for gate in HARD_GATES if treat_gates[gate] == 'fail']
    if failed:
        return NO_GO, failed[0] + ' regression in treatment arm'
    if kind == 'exclusion' and treatment['economy_bias'] is True:
        return NO_GO, 'economy bias on excluded task'
    independence = treatment['reviewer_independence']
    if independence == 'FAIL':
        return NO_GO, 'reviewer independence violated'
    if independence == 'N/A' and not treatment.get('capability_limitation'):
        return INCONCLUSIVE, 'N/A independence without documented limitation'
    return GO, 'no hard regression'


def write_manifest(out_dir, record):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'manifest.json').write_text(json.dumps(record, indent=2, sort_keys=True), encoding='utf-8')
    return out / 'manifest.json'


def run_pair(args):
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        print(INVALID_EXPERIMENT + ': non-empty output root refused; nothing was written')
        return 2
    try:
        arm_info = check_arms(args.task_dir, args.baseline_stack, args.treatment_stack, args.allow or [])
    except QualificationError as exc:
        write_manifest(out, {'case': args.case, 'verdict': INVALID_EXPERIMENT, 'reason': str(exc)})
        print(INVALID_EXPERIMENT + ': ' + str(exc))
        return 2
    arms = {}
    for name, stack in (('baseline', args.baseline_stack), ('treatment', args.treatment_stack)):
        home = out / (name + '-home')
        workspace = out / (name + '-workspace')
        home.mkdir(parents=True, exist_ok=True)
        shutil.copytree(args.task_dir, workspace / 'task', dirs_exist_ok=True)
        result = run_arm(shlex.split(args.cmd, posix=(os.name != 'nt')), workspace, home, {'IE_METHOD_STACK': str(stack), 'IE_ARM': name}, args.timeout)
        arms[name] = {'stack': str(stack), 'home': str(home), 'workspace': str(workspace), 'cmd': args.cmd, 'result': result}
    verdict, reason = score_pair(arms['baseline']['result'], arms['treatment']['result'], args.case, args.kind)
    record = {'case': args.case, 'kind': args.kind, 'task_digest': arm_info['task_digest'], 'baseline_method_digest': arm_info['baseline_method_digest'], 'treatment_method_digest': arm_info['treatment_method_digest'], 'allowed_diff': arm_info['allowed_diff'], 'baseline': arms['baseline'], 'treatment': arms['treatment'], 'harness': HARNESS, 'harness_version': HARNESS_VERSION, 'model': args.model, 'temperature': args.temperature, 'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'verdict': verdict, 'reason': reason}
    write_manifest(out, record)
    print(verdict + ': ' + reason)
    return 0 if verdict == GO else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description='Paired-arm behavioral qualification.')
    parser.add_argument('--case', required=True)
    parser.add_argument('--kind', default='implementation')
    parser.add_argument('--task-dir', required=True)
    parser.add_argument('--baseline-stack', required=True)
    parser.add_argument('--treatment-stack', required=True)
    parser.add_argument('--allow', action='append', default=[])
    parser.add_argument('--cmd', required=True)
    parser.add_argument('--model', default='unknown')
    parser.add_argument('--temperature', default='unknown')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--out', required=True)
    return run_pair(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())

