#!/usr/bin/env python3
# Stdlib only. No model client, no network, no orchestration platform: the
# harness prepares isolated arms, verifies task equivalence and the
# methodology allowlist, runs one external command per arm, then scores
# hard gates before any secondary metric. Manual runs only.
#
# Each arm command must write result.json into its workspace; see
# docs/implementation-economy/qualification/README.md for the schema.
# Test without a model via the fake runner used in
# tests/implementation_economy/test_qualification_harness.py.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import shlex
import shutil
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


def tree_digest(root):
    # SHA-256 over sorted relative paths and bytes. Missing dir fails.
    digest = hashlib.sha256()
    root = Path(root)
    if not root.is_dir():
        raise QualificationError('missing tree: ' + str(root))
    names = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
    for name in names:
        digest.update(name.encode('utf-8'))
        digest.update(b'\0')
        digest.update((root / name).read_bytes())
    digest.update(str(len(names)).encode('utf-8'))
    return digest.hexdigest(), names



def file_hashes(root):
    # Map relative path to SHA-256 for every file under root.
    out = {}
    root = Path(root)
    for path in sorted(root.rglob('*')):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def check_arms(task_dir, baseline_stack, treatment_stack, allowlist):
    # Fail closed before any model call. Returns digests and the allowed diff.
    task_digest, _ = tree_digest(task_dir)
    base_files = file_hashes(baseline_stack)
    treat_files = file_hashes(treatment_stack)
    differing = sorted(n for n in set(base_files) | set(treat_files) if base_files.get(n) != treat_files.get(n))
    def is_allowed(name):
        # Allowlist entries are exact relative paths or 'dir/*' prefixes.
        return any(name == a or (a.endswith('*') and name.startswith(a[:-1])) for a in allowlist)
    allowed = [d for d in differing if is_allowed(d)]
    if len(allowed) != len(differing):
        raise QualificationError('non-allowlisted methodology difference: ' + str([d for d in differing if d not in allowed]))
    union = sorted(set(base_files) | set(treat_files))
    method_digest = hashlib.sha256(';'.join(n + ':' + (base_files.get(n) or treat_files.get(n)) for n in union).encode('utf-8')).hexdigest()
    return {'task_digest': task_digest, 'method_digest': method_digest, 'allowed_diff': allowed}


def run_arm(command, workspace, home, timeout_s=600):
    # One external process per arm with its own HOME and cwd. Returns the
    # parsed result.json, or None when the arm produced nothing usable.
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env['HOME'] = str(home)
    completed = subprocess.run(command, cwd=str(workspace), env=env, capture_output=True, text=True, timeout=timeout_s)
    result_file = workspace / 'result.json'
    if completed.returncode != 0 or not result_file.is_file():
        return None
    try:
        result = json.loads(result_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return result if isinstance(result, dict) else None



def score_pair(baseline, treatment):
    # Hard gates first. Any attributable treatment regression is NO-GO.
    # Missing output or a broken baseline is INCONCLUSIVE, never a pass.
    if not isinstance(baseline, dict) or not isinstance(treatment, dict):
        return INCONCLUSIVE, 'missing arm result'
    base_gates = baseline.get('hard_gates', {})
    treat_gates = treatment.get('hard_gates', {})
    for gate in HARD_GATES:
        if base_gates.get(gate) == 'fail':
            return INCONCLUSIVE, 'baseline gate failed: ' + gate
    for gate in HARD_GATES:
        if treat_gates.get(gate) == 'fail':
            return NO_GO, gate + ' regression in treatment arm'
    if treatment.get('kind') == 'exclusion' and treatment.get('economy_bias') is True:
        return NO_GO, 'economy bias on excluded task'
    independence = treatment.get('reviewer_independence', 'PASS')
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
    try:
        arm_info = check_arms(args.task_dir, args.baseline_stack, args.treatment_stack, args.allow or [])
    except QualificationError as exc:
        record = {'case': args.case, 'verdict': INVALID_EXPERIMENT, 'reason': str(exc)}
        write_manifest(args.out, record)
        print(INVALID_EXPERIMENT + ': ' + str(exc))
        return 2
    pair_root = Path(args.out)
    arms = {}
    for name, stack in (('baseline', args.baseline_stack), ('treatment', args.treatment_stack)):
        home = pair_root / (name + '-home')
        workspace = pair_root / (name + '-workspace')
        home.mkdir(parents=True, exist_ok=True)
        shutil.copytree(args.task_dir, workspace / 'task', dirs_exist_ok=True)
        raw_cmd = args.baseline_cmd if name == 'baseline' else args.treatment_cmd
        cmd = shlex.split(raw_cmd, posix=(os.name != 'nt'))
        arms[name] = {'stack': str(stack), 'home': str(home), 'workspace': str(workspace), 'result': run_arm(cmd, workspace, home, args.timeout)}
    verdict, reason = score_pair(arms['baseline']['result'], arms['treatment']['result'])
    record = {'case': args.case, 'kind': args.kind, 'task_digest': arm_info['task_digest'], 'method_digest': arm_info['method_digest'], 'allowed_diff': arm_info['allowed_diff'], 'baseline': arms['baseline'], 'treatment': arms['treatment'], 'harness': HARNESS, 'harness_version': HARNESS_VERSION, 'model': args.model, 'temperature': args.temperature, 'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'verdict': verdict, 'reason': reason}
    write_manifest(args.out, record)
    print(verdict + ': ' + reason)
    return 0 if verdict == GO else 1



def main(argv=None):
    parser = argparse.ArgumentParser(description='Paired-arm behavioral qualification for Implementation Economy.')
    parser.add_argument('--case', required=True)
    parser.add_argument('--kind', default='implementation')
    parser.add_argument('--task-dir', required=True)
    parser.add_argument('--baseline-stack', required=True)
    parser.add_argument('--treatment-stack', required=True)
    parser.add_argument('--allow', action='append', default=[])
    parser.add_argument('--baseline-cmd', required=True)
    parser.add_argument('--treatment-cmd', required=True)
    parser.add_argument('--model', default='unknown')
    parser.add_argument('--temperature', default='unknown')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--out', required=True)
    return run_pair(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())

