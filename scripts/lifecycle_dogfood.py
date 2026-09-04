#!/usr/bin/env python3
"""Gate the Distribution & Lifecycle Manager with the stack's own Work Plane.

The feature that installs the Verified Work Plane should be able to survive it.
So this declares a real work contract for Distribution & Lifecycle v1 —
requirements, acceptance criteria and verification specifications whose commands
are the lifecycle suite itself — runs each verification through the production
surface, and asks `evaluate_work()` for a verdict.

Three things this is honest about.

*The anchor is agent-bootstrapped.* ADR-0006 says the runtime cannot tell a
trusted operator from a controlled agent performing the same ceremony. The same
process that wrote this work also bootstrapped the trust it is judged under, so
the verdict is evidence that the work's declared properties were checked — not
evidence that a human authorised it. The record says so in a field, not in a
footnote.

*It runs in a throwaway clone.* No trust anchor is written into the real
repository, because a reader finding one there could reasonably mistake it for
a project's genuine anchor.

*It cannot make itself pass.* Every verdict comes from `evaluate_work()`. This
script constructs no `TrustVerdict`, no `FreshnessResult` and no
`VerificationEvidence`, and never calls the pure `converge()` kernel.

Usage:
    python scripts/lifecycle_dogfood.py
    python scripts/lifecycle_dogfood.py --output docs/qualification/lifecycle-v1-dogfood.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from ainative_workplane.bootstrap import bootstrap, creation_approval_path  # noqa: E402
from ainative_workplane.contracts import generate_uid  # noqa: E402
from ainative_workplane.controller import WorkController  # noqa: E402
from ainative_workplane.evaluator import evaluate_work, run_verification  # noqa: E402
from ainative_workplane.trust import approval_root_commitment, policy_commitment  # noqa: E402

DIGEST = "a" * 64
PREDICATE = "recorded_owner_ack"

# One requirement per invariant ADR-0009 fixes, and the suite that decides it.
# The command is what runs; the covered paths are what it is a claim about.
REQUIREMENTS = (
    {
        "key": "profiles",
        "statement": "Verified extends Standard, and Standard never depends on Verified.",
        "criterion": "The resolved component set for verified contains every standard "
                     "component, the verified profile restates none of them, and "
                     "installing Standard loads no Work Plane module.",
        "command": "profiles",
        "argv": ["-m", "unittest", "tests.test_lifecycle_ownership.OwnershipDeclarations",
                 "tests.test_lifecycle_cli.LayerBoundary", "-v"],
        "scope": ["tests/test_lifecycle_ownership.py", "tests/test_lifecycle_cli.py"],
        "covers": ["ainative/lifecycle/manifest.py", "ainative/cli.py"],
    },
    {
        "key": "transitions",
        "statement": "Every declared profile transition is idempotent, reversible and "
                     "non-destructive.",
        "criterion": "The full transition matrix and both round trips hold, a repeated "
                     "operation is a no-op, and a downgrade preserves the Verified history "
                     "byte for byte.",
        "command": "transitions",
        "argv": ["-m", "unittest", "tests.test_lifecycle_matrix", "-v"],
        "scope": ["tests/test_lifecycle_matrix.py"],
        "covers": ["ainative/lifecycle/installer.py", "ainative/lifecycle/planner.py",
                   "ainative/lifecycle/uninstaller.py"],
    },
    {
        "key": "ownership",
        "statement": "No lifecycle operation destroys content the stack did not write.",
        "criterion": "A user-edited managed file survives install, update, downgrade and "
                     "uninstall; a template copy is never overwritten; and a config file "
                     "the stack does not own is restored byte for byte.",
        "command": "ownership",
        "argv": ["-m", "unittest", "tests.test_lifecycle_ownership", "-v"],
        "scope": ["tests/test_lifecycle_ownership.py"],
        "covers": ["ainative/lifecycle/digest.py", "ainative/lifecycle/external.py",
                   "ainative/lifecycle/planner.py"],
    },
    {
        "key": "transactions",
        "statement": "An interrupted lifecycle mutation leaves the old valid state or the "
                     "new one, never a state between them.",
        "criterion": "Interruption after the backup, partway through, mid external-config "
                     "mutation and before the commit all leave a recoverable project; "
                     "repair restores it; and two mutations cannot interleave.",
        "command": "transactions",
        "argv": ["-m", "unittest", "tests.test_lifecycle_transactions", "-v"],
        "scope": ["tests/test_lifecycle_transactions.py"],
        "covers": ["ainative/lifecycle/transaction.py", "ainative/lifecycle/lock.py",
                   "ainative/lifecycle/recovery.py", "ainative/lifecycle/legacy.py"],
    },
    {
        "key": "updates",
        "statement": "An update is transactional, integrity-checked, and never silent.",
        "criterion": "Detection is cached and non-fatal offline, a mismatched archive "
                     "digest stops the update before any write, a user-modified file "
                     "keeps its content, and rollback restores the previous assets.",
        "command": "updates",
        "argv": ["-m", "unittest", "tests.test_lifecycle_update", "-v"],
        "scope": ["tests/test_lifecycle_update.py"],
        "covers": ["ainative/lifecycle/updater.py", "ainative/lifecycle/provider.py",
                   "ainative/lifecycle/version.py"],
    },
    {
        "key": "safety",
        "statement": "No manifest, install state or release archive can make the lifecycle "
                     "write or delete outside the project root.",
        "criterion": "Traversal, absolute, drive, UNC and link-escape paths are refused; a "
                     "tampered state cannot delete an outside file; and an archive naming "
                     "a traversal path is refused before extraction.",
        "command": "safety",
        "argv": ["-m", "unittest", "tests.test_lifecycle_security", "-v"],
        "scope": ["tests/test_lifecycle_security.py"],
        "covers": ["ainative/lifecycle/paths.py", "ainative/lifecycle/manifest.py",
                   "ainative/lifecycle/updater.py"],
    },
    {
        "key": "cli",
        "statement": "Every command is usable without a terminal and returns a documented "
                     "exit code.",
        "criterion": "Each documented command emits parseable JSON, a confirmation refuses "
                     "rather than prompting without a TTY, exit codes match the declared "
                     "table, and the Verified commands still reach their own engine.",
        "command": "cli",
        "argv": ["-m", "unittest", "tests.test_lifecycle_cli", "-v"],
        "scope": ["tests/test_lifecycle_cli.py"],
        "covers": ["ainative/cli.py", "ainative/lifecycle/errors.py",
                   "ainative/lifecycle/status.py"],
    },
    {
        "key": "non_vacuity",
        "statement": "Every protection the lifecycle claims actually blocks something.",
        "criterion": "Reverting each guard in a scratch copy makes its test fail.",
        "command": "non_vacuity",
        "argv": ["scripts/lifecycle_non_vacuity.py", "--json"],
        # Not `unittest`: this command emits its own structured record, and
        # declaring an adapter that cannot read it made the Work Plane report
        # SUSPICIOUS_VERIFICATION on a run that had actually passed. The
        # minimum is derived from the case list, so adding a guard without
        # widening the contract is a refusal rather than a quiet pass.
        "substance": {"type": "json", "minimum_observations": None},
        "scope": ["scripts/lifecycle_non_vacuity.py"],
        "covers": ["ainative/lifecycle/digest.py", "ainative/lifecycle/paths.py",
                   "ainative/lifecycle/transaction.py", "ainative/lifecycle/planner.py"],
    },
)


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


def _policy(commitment_placeholder: str = DIGEST) -> dict[str, Any]:
    return {
        "schema_name": "project_policy", "schema_version": 1,
        "approval_predicate": {"predicate_id": PREDICATE,
                               "policy_digest": commitment_placeholder},
        "required_mutation_facts": {"git_recorded": True},
        "required_evidence_facts": {"git_recorded": True},
        "waiver_approval_rule": {"predicate_id": PREDICATE,
                                 "policy_digest": commitment_placeholder},
        "human_approval_rule": {"predicate_id": PREDICATE,
                                "policy_digest": commitment_placeholder},
        "promotion_policy": "explicit",
    }


class DogfoodWork:
    """A throwaway governed clone of this repository, carrying a real contract."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "repo"
        # A local clone, so the verifications run against this branch's real
        # sources rather than a fixture that could drift from them.
        subprocess.run(["git", "clone", "--quiet", "--local", "--no-hardlinks",
                        str(REPO), str(self.repo)], check=True, capture_output=True)
        git(self.repo, "config", "user.email", "lifecycle-dogfood@example.invalid")
        git(self.repo, "config", "user.name", "Lifecycle Dogfood")
        self.work = self.repo / ".ai-native" / "work" / "distribution-lifecycle-v1"

        self.uids = {item["key"]: {"requirement": generate_uid("req"),
                                   "criterion": generate_uid("ac"),
                                   "specification": generate_uid("verify"),
                                   "task": generate_uid("task")}
                     for item in REQUIREMENTS}

        self.policy = _policy()
        commitment = policy_commitment(self.policy)
        for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
            self.policy[field]["policy_digest"] = commitment
        self.commitment = commitment

        self.approval_root = {
            "schema_name": "approval_root", "schema_version": 1, "uid": generate_uid("root"),
            "root_digest": DIGEST, "policy_digest": commitment,
            "root_provenance": "GIT_RECORDED",
            "bootstrap": {"initialized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "initialized_by": "lifecycle-dogfood"},
        }
        self.approval_root["root_digest"] = approval_root_commitment(self.approval_root)

        self.anchor = bootstrap(self.repo, approval_root=self.approval_root,
                                policy=self.policy, initialized_by="lifecycle-dogfood",
                                predicate_id=PREDICATE)
        self.commit("project trust anchor")

        declared = self.artifacts()
        self.admit(declared)
        WorkController(self.work).create(declared)
        self.commit("work contract, revision 1")

    def commit(self, message: str) -> None:
        git(self.repo, "add", "-A")
        pending = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                                 check=True, capture_output=True, text=True)
        if pending.stdout.strip():
            git(self.repo, "commit", "-m", message)

    def admit(self, artifacts: dict[str, Any]) -> None:
        anchor = json.loads(Path(self.anchor).read_text(encoding="utf-8"))
        approval = {
            "schema_name": "work_creation_approval", "schema_version": 1,
            "uid": generate_uid("approval"),
            "trust_uid": anchor["uid"], "trust_digest": anchor["trust_digest"],
            "genesis_digest": WorkController(self.work).normative_digest(artifacts),
            "predicate_id": anchor["bootstrap_predicate"]["predicate_id"],
            "approved_by": "lifecycle-dogfood",
            "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        path = creation_approval_path(self.work)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(approval), encoding="utf-8")
        self.commit("work creation approval")

    def registry(self) -> dict[str, Any]:
        commands = {}
        for item in REQUIREMENTS:
            substance = dict(item.get("substance")
                             or {"type": "unittest", "minimum_observations": 1})
            if substance.get("minimum_observations") is None:
                from lifecycle_non_vacuity import CASES

                substance["minimum_observations"] = len(CASES)
            commands[item["command"]] = {
                "argv": [sys.executable, *item["argv"]],
                # The lifecycle suite spawns child processes; a budget sized to
                # a unit test would report a timeout as a failure and call that
                # evidence.
                "timeout_seconds": 1800,
                "substance": substance,
            }
        return {"schema_name": "command_registry", "schema_version": 1, "commands": commands}

    def artifacts(self) -> dict[str, Any]:
        requirements, criteria, tasks, specifications = [], [], [], []
        for item in REQUIREMENTS:
            uids = self.uids[item["key"]]
            requirements.append({
                "schema_name": "requirements", "schema_version": 1,
                "uid": uids["requirement"], "statement": item["statement"],
                "acceptance_criteria": [{"uid": uids["criterion"], "digest": DIGEST}]})
            criteria.append({
                "schema_name": "acceptance_criteria", "schema_version": 1,
                "uid": uids["criterion"],
                "requirement": {"uid": uids["requirement"], "digest": DIGEST},
                "criterion": item["criterion"],
                "verification_specifications": [{"uid": uids["specification"],
                                                 "digest": DIGEST}]})
            tasks.append({
                "schema_name": "tasks", "schema_version": 1, "uid": uids["task"],
                "requirements": [{"uid": uids["requirement"], "digest": DIGEST}],
                "implementation_paths": item["covers"]})
            specifications.append({
                "schema_name": "verification_specification", "schema_version": 1,
                "uid": uids["specification"],
                "acceptance_criteria": [{"uid": uids["criterion"], "digest": DIGEST}],
                "command_registry": {"uid": generate_uid("work"), "digest": DIGEST},
                "relationship": "black_box", "execution_scope": item["scope"],
                "covered_implementation_paths": item["covers"], "dependencies": [],
                "substance_requirement": "unittest",
                "required_evidence_provenance": "GIT_RECORDED",
                "command": item["command"]})
        return {
            "requirements": requirements, "acceptance_criteria": criteria, "tasks": tasks,
            "verification_specifications": specifications,
            "project_policy": self.policy, "approval_root": self.approval_root,
            "command_registry": self.registry(),
        }


def run(output: Path | None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ainative-dogfood-",
                                     ignore_cleanup_errors=True) as scratch:
        work = DogfoodWork(Path(scratch))
        verifications = []
        for item in REQUIREMENTS:
            uid = work.uids[item["key"]]["specification"]
            started = time.time()
            evidence = run_verification(work.work, work.repo, uid)
            work.commit(f"verification evidence: {item['command']}")
            verifications.append({
                "requirement": item["key"], "specification": uid,
                "command": item["command"], "result": evidence.result,
                "duration_seconds": round(time.time() - started, 1),
                "evidence_uid": evidence.uid,
            })

        evaluation = evaluate_work(work.work, work.repo)
        verdict = evaluation.verdict
        head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
        return {
            "schema_version": 1,
            "subject": "Distribution & Lifecycle Manager v1",
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_commit": head,
            "surface": "evaluate_work",
            "authority": "production_boundary",
            # Stated, not implied: the same process bootstrapped the trust it is
            # judged under, which ADR-0006 says the runtime cannot distinguish
            # from a human ceremony. This is evidence the declared properties
            # were checked, not evidence anyone authorised them.
            "trust_provenance": "agent_bootstrapped_in_a_throwaway_clone",
            "authority_claim": "none - dogfood evidence only",
            "contract_digest": evaluation.contract_digest,
            "verdict": verdict.verdict,
            "reason": verdict.reason,
            "fingerprint": verdict.fingerprint,
            "requirements": len(REQUIREMENTS),
            "verifications": verifications,
            "gaps": [{"code": gap.code, "uid": gap.uid, "detail": gap.detail}
                     for gap in verdict.gaps],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path,
                        help="write the record here as well as to stdout")
    args = parser.parse_args()

    record = run(args.output)
    encoded = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0 if record["verdict"] == "CONVERGED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
