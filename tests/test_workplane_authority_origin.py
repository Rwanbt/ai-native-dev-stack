"""Authority attacks A72-A107: who may create evidence, and who may change the rules.

The A54-A70 matrix proved that the evaluator does not accept authority from its
caller's arguments. These cases ask the next question: can a caller manufacture
the things the evaluator does accept — a verification result, a provenance
claim, an approval, or a weaker rule to be measured against.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative_workplane.bootstrap import BootstrapError, anchor_refusal, bootstrap, creation_approval_path, trust_commitment
from ainative_workplane.contracts import canonical_digest, generate_uid
from ainative_workplane.controller import ControllerError, WorkController
from ainative_workplane.evaluator import SUCCESS_CONDITION, EvaluationError, evaluate_work
from ainative_workplane.evidence import VerificationEvidence
from ainative_workplane.predicates import predicate_refusal
from ainative_workplane.provenance import ProvenanceFacts, observe, signature_signers
from ainative_workplane.snapshot import build_repository_snapshot, snapshot_reference
from ainative_workplane.trust import approval_root_commitment, evaluate_trust, policy_commitment, successor_commitment
from tests.test_workplane_authority import GovernedWork, git

ESTABLISHED = ProvenanceFacts(git_recorded=True, signature_verified=True, local_dirty=False)
DIGEST = "a" * 64


class SimpleEvidence:
    """The minimum `evaluate_trust` reads, so a chain rule can be asserted alone."""

    def __init__(self, root, policy_digest):
        self.artifact = {
            "approval_root": {"uid": root["uid"], "digest": root["root_digest"]},
            "policy_digest": policy_digest,
        }


def forged_run(work: GovernedWork, **overrides):
    """Build a complete, schema-valid PASS run without executing anything.

    Every value is read from committed state and from the checkout, which is
    exactly what an agent with write access to the work directory can do.
    """

    manifest, artifacts = WorkController(work.work).load_committed_artifacts()
    specification = artifacts["verification_specifications"][0]
    policy_digest = policy_commitment(artifacts["project_policy"])
    registry_digest = canonical_digest(artifacts["command_registry"])
    root = artifacts["approval_root"]
    contract_digest = canonical_digest({name: artifacts.get(name, []) for name in SUCCESS_CONDITION})
    snapshot = build_repository_snapshot(
        work.repo,
        scope=specification["execution_scope"],
        dependency_paths=specification["covered_implementation_paths"],
        command_registry_digest=registry_digest,
        policy_digest=policy_digest,
    )
    record = {
        "schema_name": "verification_run", "schema_version": 1, "uid": generate_uid("run"),
        "work": {"uid": manifest["work_uid"], "digest": contract_digest},
        "contract_revision": manifest["revision"], "contract_digest": contract_digest,
        "verification_specification": {"uid": specification["uid"], "digest": canonical_digest(specification)},
        "command_registry_digest": registry_digest, "policy_digest": policy_digest,
        "approval_root": {"uid": root["uid"], "digest": root["root_digest"]},
        "repository_snapshot": snapshot_reference(snapshot),
        "snapshot_content_digest": snapshot["content_digest"],
        "snapshot_dependency_digest": snapshot["dependency_digest"],
        "snapshot_head": snapshot["head"],
        "producer": "ainative-workplane", "producer_version": "0.1.0",
        "command": "check", "result": "PASS", "exit_code": 0,
        "started_at": "2026-09-03T00:00:00Z", "finished_at": "2026-09-03T00:00:01Z", "duration_ms": 1,
        "stdout_digest": "0" * 64, "stderr_digest": "0" * 64,
        "substance_metadata": {"adapter": "unittest", "tests_executed": 999},
        "evidence_provenance": "GIT_RECORDED",
    }
    record.update(overrides)
    return record


class EvidenceOriginTests(unittest.TestCase):
    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def test_a72_a_hand_written_run_is_never_read(self):
        work = self.governed()
        runs = work.work / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        forged = forged_run(work)
        (runs / "forged.json").write_text(json.dumps(forged), encoding="utf-8")
        # Every digest in the file is correct and the checkout is clean. The
        # only thing missing is that no command was ever run — so the file must
        # carry no weight either way.
        evaluation = evaluate_work(work.work, work.repo)
        judged = {assessment.evidence_uid for assessment in evaluation.assessments}
        self.assertNotIn(forged["uid"], judged, "a hand-written run was judged as evidence")
        self.assertEqual(1, len(evaluation.assessments), "exactly the one executable specification is judged")

    def test_a72_a_forgery_cannot_hide_a_verification_that_fails(self):
        work = self.governed()
        failing = "import sys\nprint('Ran 1 test in 0.0s')\nprint('FAILED (failures=1)')\nsys.exit(1)\n"
        (work.repo / "tests" / "check.py").write_text(failing, encoding="utf-8")
        import subprocess
        subprocess.run(["git", "-C", str(work.repo), "commit", "-am", "break the check"], check=True, capture_output=True)
        runs = work.work / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / "forged.json").write_text(json.dumps(forged_run(work)), encoding="utf-8")
        evaluation = evaluate_work(work.work, work.repo)
        self.assertNotEqual("CONVERGED", evaluation.verdict.verdict, "a forged PASS masked a failing verification")

    def test_a73_the_authoritative_api_takes_no_evidence_directory(self):
        from inspect import signature

        self.assertEqual({"work_dir", "repository_root"}, set(signature(evaluate_work).parameters))



class RegistrySchemaTests(unittest.TestCase):
    """A89, A90: one validator, so the controller and the runner agree."""

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def malformed(self, work):
        return {
            "A89 no commands": {"schema_name": "command_registry", "schema_version": 1, "commands": {}},
            "A89 shell requested": {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": ["echo"], "shell": True}}},
            "A89 empty argv": {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": []}}},
            "A89 impossible timeout": {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": ["echo"], "timeout_seconds": 0}}},
            "A89 unknown substance": {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": ["echo"], "substance": {"type": "junit"}}}},
        }

    def test_a89_a_malformed_registry_cannot_become_committed_authority(self):
        work = self.governed()
        for case, registry in self.malformed(work).items():
            with self.subTest(case=case):
                with self.assertRaises(ControllerError) as refused:
                    WorkController(work.work).mutate(1, {"command_registry": registry}, approval=work.record_approval_for_change({"command_registry": registry}))
                self.assertIn("INVALID_NORMATIVE_ARTIFACT:command_registry", str(refused.exception))

    def test_a90_what_the_controller_accepts_the_runner_accepts(self):
        from ainative_workplane.runner import RunnerError, load_registry
        from ainative_workplane.contracts import ContractError, validate_normative

        work = self.governed()
        for case, registry in self.malformed(work).items():
            with self.subTest(case=case):
                with self.assertRaises(ContractError):
                    validate_normative("command_registry", registry)
                with self.assertRaises(RunnerError):
                    load_registry(registry)
        # And the committed one satisfies both, by construction.
        _, artifacts = WorkController(work.work).load_committed_artifacts()
        validate_normative("command_registry", artifacts["command_registry"])
        self.assertEqual(artifacts["command_registry"], load_registry(artifacts["command_registry"]))



class ApprovalOriginTests(unittest.TestCase):
    """A91, A92: the key to the mutation bar may not be cut by the actor it controls."""

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def weaker_registry(self, work):
        _, committed = WorkController(work.work).load_committed_artifacts()
        weak = json.loads(json.dumps(committed["command_registry"]))
        weak["commands"]["check"]["argv"] = [sys.executable, "-c", "print('Ran 1 test in 0.0s'); print('OK')"]
        return weak, {**committed, "command_registry": weak}

    def test_a91_an_approval_the_caller_invented_authorizes_nothing(self):
        work = self.governed()
        weak, candidate = self.weaker_registry(work)
        invented = work.approval_record(candidate)
        # Never written anywhere, never recorded: a Python object asserting that
        # a release board agreed.
        with self.assertRaises(ControllerError) as refused:
            WorkController(work.work).mutate(1, {"command_registry": weak}, approval=invented)
        self.assertIn("UNAUTHORIZED_MUTATION", str(refused.exception))
        self.assertEqual(1, WorkController(work.work).read()["revision"])

    def test_a91_an_approval_written_but_not_recorded_authorizes_nothing(self):
        work = self.governed()
        weak, candidate = self.weaker_registry(work)
        loose = work.root / "approval.json"
        loose.write_text(json.dumps(work.approval_record(candidate)), encoding="utf-8")
        with self.assertRaisesRegex(ControllerError, "UNAUTHORIZED_MUTATION"):
            WorkController(work.work).mutate(1, {"command_registry": weak}, approval=loose)

    def test_a92_a_recorded_approval_authorizes_exactly_its_own_candidate(self):
        work = self.governed()
        weak, candidate = self.weaker_registry(work)
        approval = work.record_approval(candidate)
        _, other = self.weaker_registry(work)
        other["command_registry"]["commands"]["check"]["timeout_seconds"] = 11
        with self.assertRaisesRegex(ControllerError, "UNAUTHORIZED_MUTATION"):
            WorkController(work.work).mutate(1, {"command_registry": other["command_registry"]}, approval=approval)
        self.assertEqual(2, WorkController(work.work).mutate(1, {"command_registry": weak}, approval=approval)["revision"])


class AuthorityRaceTests(unittest.TestCase):
    """A93: authority that moves while the verification runs."""

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def test_a93_a_command_that_rewrites_the_authority_cannot_converge(self):
        work = self.governed()
        target = str(work.work / "manifest.json").replace("\\", "\\\\")
        tamper = (
            "import json, pathlib\n"
            "p = pathlib.Path(r'" + target + "')\n"
            "m = json.loads(p.read_text())\n"
            "m['revision'] = 99\n"
            "p.write_text(json.dumps(m))\n"
            "print('Ran 1 test in 0.0s')\n"
            "print('OK')\n"
        )
        (work.repo / "tests" / "check.py").write_text(tamper, encoding="utf-8")
        work.commit_governed_state()
        evaluation = evaluate_work(work.work, work.repo)
        self.assertNotEqual("CONVERGED", evaluation.verdict.verdict, "a command rewrote the authority and still converged")
        self.assertIn("AUTHORITY_CHANGED_DURING_EVALUATION", [gap.code for gap in evaluation.verdict.gaps])



def weaker_registry(work):
    """A registry whose declared command runs something that passes."""

    (work.repo / "tests" / "easy.py").write_text("print('Ran 1 test in 0.001s'); print('OK')\n", encoding="utf-8")
    work.commit_governed_state()
    registry = work.registry()
    registry["commands"]["check"]["argv"] = [sys.executable, "tests/easy.py"]
    return {"command_registry": registry}


def make_the_check_fail(work):
    (work.repo / "tests" / "check.py").write_text("import sys\nprint('Ran 1 test in 0.001s')\nprint('FAILED (failures=1)')\nsys.exit(1)\n", encoding="utf-8")
    work.commit_governed_state()


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required to exercise a real signature predicate")
class ApprovalPredicateTests(unittest.TestCase):
    """A94: recorded is not approved.

    The third round made the mutation approval an artifact, so an actor could
    no longer hand the controller an object it had just built. It could still
    write that object to a file and commit it, and under a policy whose
    predicate was *named* `review` while requiring only `git_recorded`, that
    counted. The predicate was a label. These cases ask whether it is a
    mechanism.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def test_a94_a_self_recorded_approval_does_not_satisfy_an_independent_predicate(self):
        work = self.governed(predicate="signature", signing=True)
        make_the_check_fail(work)
        self.assertEqual("NOT_CONVERGED", evaluate_work(work.work, work.repo).verdict.verdict)

        # The actor has write access and commit rights. It does not have the
        # key, which is the entire difference the predicate is supposed to
        # make. It builds the exact approval its own weakened state needs.
        weaker = weaker_registry(work)
        approval = work.record_approval_for_change(weaker, signed=False)
        with self.assertRaises(ControllerError) as refusal:
            WorkController(work.work).mutate(1, weaker, approval=approval)
        self.assertIn("signature_verified", str(refusal.exception))

        # And nothing moved: the failing verification is still failing.
        work.commit_governed_state()
        self.assertEqual("NOT_CONVERGED", evaluate_work(work.work, work.repo).verdict.verdict)
        self.assertEqual(1, WorkController(work.work).read()["revision"])

    def test_a94_the_same_mutation_is_accepted_when_the_predicate_is_actually_satisfied(self):
        """The control. Without it, A94 could pass because nothing works."""

        work = self.governed(predicate="signature", signing=True)
        make_the_check_fail(work)
        weaker = weaker_registry(work)
        approval = work.record_approval_for_change(weaker, signed=True)
        WorkController(work.work).mutate(1, weaker, approval=approval)
        work.commit_governed_state()
        self.assertEqual(2, WorkController(work.work).read()["revision"])
        self.assertEqual("CONVERGED", evaluate_work(work.work, work.repo).verdict.verdict)

    def test_a94_a_predicate_no_provider_implements_is_never_satisfied(self):
        """A policy cannot acquire authority by naming a mechanism."""

        self.assertIsNone(predicate_refusal("recorded_owner_ack", ProvenanceFacts(git_recorded=True, local_dirty=False)))
        for invented in ("review", "release-board", "human-signoff", "", None):
            self.assertIsNotNone(predicate_refusal(invented, ProvenanceFacts(git_recorded=True, signature_verified=True, ci_verified=True, git_reviewed=True, local_dirty=False)))


class GenesisTrustTests(unittest.TestCase):
    """A95: who decided what this project trusts.

    Every N to N+1 protection held while the actor could simply choose N. A
    work contract is now created *under* a project trust anchor, and creating a
    directory is no longer an act of governance.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def codes(self, evaluation):
        return [gap.code for gap in evaluation.verdict.gaps]

    def test_a95_a_work_the_project_never_pinned_is_unevaluable(self):
        work = self.governed(anchor=False)
        evaluation = evaluate_work(work.work, work.repo)
        self.assertEqual("INVALID", evaluation.verdict.verdict)
        self.assertIn("PROJECT_TRUST_UNINITIALIZED", self.codes(evaluation))

    def test_a95_a_second_work_cannot_bring_a_root_of_its_own(self):
        work = self.governed()
        stranger = dict(work.approval_root, uid=generate_uid("root"), root_provenance="UNTRACKED")
        stranger["root_digest"] = approval_root_commitment(stranger)
        sibling = work.repo / ".ai-native" / "work" / "w2"
        declared = work.artifacts(approval_root=stranger)
        work.admit(sibling, declared)
        with self.assertRaises(ControllerError) as refusal:
            WorkController(sibling).create(declared)
        self.assertIn("UNGOVERNED_GENESIS", str(refusal.exception))

    def test_a95_a_second_work_under_the_pinned_root_is_permitted(self):
        """The control: governance is a bar, not a wall."""

        work = self.governed()
        sibling = work.repo / ".ai-native" / "work" / "w2"
        declared = work.artifacts()
        work.admit(sibling, declared)
        manifest = WorkController(sibling).create(declared)
        self.assertEqual(1, manifest["revision"])

    def test_a95_a_governed_project_never_re_bootstraps(self):
        work = self.governed()
        with self.assertRaises(BootstrapError) as refusal:
            bootstrap(work.repo, approval_root=work.approval_root, policy=work.policy, initialized_by="the actor", predicate_id="recorded_owner_ack")
        self.assertIn("ALREADY_INITIALIZED", str(refusal.exception))

    @unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required to exercise a real signature predicate")
    def test_a95_an_anchor_the_actor_only_recorded_does_not_satisfy_signature(self):
        work = self.governed(predicate="signature", signing=True)
        self.assertEqual("CONVERGED", evaluate_work(work.work, work.repo).verdict.verdict)
        # The actor rewrites the anchor. The content still parses and still
        # commits to itself; the last commit that touched it is unsigned,
        # because the actor has no key.
        Path(work.anchor).write_text(Path(work.anchor).read_text(encoding="utf-8") + "\n", encoding="utf-8")
        work.commit_governed_state(signed=False)
        evaluation = evaluate_work(work.work, work.repo)
        self.assertEqual("INVALID", evaluation.verdict.verdict)
        self.assertIn("PROJECT_TRUST_UNVERIFIED", self.codes(evaluation))

    def test_a95_an_unreadable_anchor_never_reads_as_absent(self):
        work = self.governed()
        Path(work.anchor).write_text("{not json", encoding="utf-8")
        work.commit_governed_state()
        evaluation = evaluate_work(work.work, work.repo)
        self.assertEqual("INVALID", evaluation.verdict.verdict)
        self.assertIn("PROJECT_TRUST_INVALID", self.codes(evaluation))


class CommittedRootHistoryTests(unittest.TestCase):
    """A96: a directory is not a commit.

    Crash consistency deliberately permits a promoted revision whose manifest
    was never replaced. Reading roots by listing `revisions/` therefore read
    authority out of a write that never happened.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def rotate(self, work, *, revision=1, marker="SIGNED", injector=None):
        """Commit a proper root transition into the next revision."""

        _, committed = WorkController(work.work).load_committed_artifacts()
        rotated = work.successor_root(committed["approval_root"], marker=marker)
        changes = {"approval_root": rotated}
        approval = work.record_approval_for_change(changes)
        WorkController(work.work, failure_injector=injector).mutate(revision, changes, approval=approval)
        work.commit_governed_state()
        return rotated

    def test_a96_a_root_from_an_uncommitted_revision_is_not_history(self):
        work = self.governed()

        def crash(step):
            if step == "before_manifest_replace":
                raise RuntimeError("power loss between promotion and commit")

        with self.assertRaises(RuntimeError):
            self.rotate(work, injector=crash)
        work.commit_governed_state()
        controller = WorkController(work.work)
        self.assertEqual(1, controller.read()["revision"])
        # The directory is there. That is exactly the point.
        self.assertTrue((work.work / "revisions" / "2" / "approval_root.json").is_file())
        history = controller.root_history()
        self.assertEqual([work.approval_root["root_digest"]], [entry["root_digest"] for entry in history])

    def test_a96_a_committed_rotation_is_history(self):
        """The control: the chain must still carry what really was committed."""

        work = self.governed()
        rotated = self.rotate(work)
        history = WorkController(work.work).root_history()
        self.assertEqual([work.approval_root["root_digest"], rotated["root_digest"]], [entry["root_digest"] for entry in history])

    def test_a96_a_root_swapped_under_a_committed_chain_entry_is_dropped(self):
        """The chain records a digest, so a historical file cannot be exchanged.

        The current revision is already protected by the manifest pointers. An
        *older* revision is not pointed at by the current manifest at all, and
        before the chain existed nothing checked what its root said.
        """

        work = self.governed()
        self.rotate(work, revision=1, marker="SIGNED")
        self.rotate(work, revision=2, marker="CI_APPROVED")
        self.assertEqual(3, len(WorkController(work.work).root_history()))
        swapped = work.successor_root(work.approval_root, marker="UNTRACKED")
        (work.work / "revisions" / "2" / "approval_root.json").write_text(json.dumps(swapped), encoding="utf-8")
        self.assertEqual(2, len(WorkController(work.work).root_history()))


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required to exercise a real signature predicate")
class InitialContractAdmissionTests(unittest.TestCase):
    """A97: who decided what this work must accomplish.

    Round 4 stopped a new work from inventing its own root. It did not stop the
    actor from writing revision 1. Requirements, acceptance criteria and
    verification specifications are success conditions -- that is why the
    mutation bar covers all of them -- so leaving the first revision to whoever
    created the directory leaves the bar to the party it constrains.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def trivial_contract(self, work):
        """A contract the actor would choose for itself: easy, and satisfied."""

        (work.repo / "tests" / "trivial.py").write_text("print('Ran 1 test in 0.0s'); print('OK')\n", encoding="utf-8")
        work.commit_governed_state()
        artifacts = work.artifacts()
        registry = work.registry()
        registry["commands"]["check"]["argv"] = [sys.executable, "tests/trivial.py"]
        artifacts["command_registry"] = registry
        artifacts["requirements"] = [dict(artifacts["requirements"][0], statement="nothing in particular")]
        artifacts["verification_specifications"] = [work.specification(execution_scope=["tests/trivial.py"])]
        return artifacts

    def test_a97_an_initial_contract_nobody_admitted_is_refused(self):
        work = self.governed(predicate="signature", signing=True)
        sibling = work.repo / ".ai-native" / "work" / "easy"
        with self.assertRaises(ControllerError) as refusal:
            WorkController(sibling).create(self.trivial_contract(work))
        self.assertIn("UNADMITTED_WORK", str(refusal.exception))

    def test_a97_an_actor_cannot_admit_its_own_initial_contract(self):
        work = self.governed(predicate="signature", signing=True)
        sibling = work.repo / ".ai-native" / "work" / "easy"
        declared = self.trivial_contract(work)
        # The actor writes the exact admission its own contract needs and
        # commits it. It has commit rights; it does not have the key.
        work.admit(sibling, declared, signed=False)
        with self.assertRaises(ControllerError) as refusal:
            WorkController(sibling).create(declared)
        self.assertIn("signature_verified", str(refusal.exception))

    def test_a97_a_work_whose_admission_disappears_stops_being_authoritative(self):
        """The evaluator asks the question too, not only the controller."""

        work = self.governed(predicate="signature", signing=True)
        self.assertEqual("CONVERGED", evaluate_work(work.work, work.repo).verdict.verdict)
        creation_approval_path(work.work).unlink()
        work.commit_governed_state()
        evaluation = evaluate_work(work.work, work.repo)
        self.assertEqual("INVALID", evaluation.verdict.verdict)
        self.assertIn("WORK_NOT_ADMITTED", [gap.code for gap in evaluation.verdict.gaps])

    def test_a97_an_admission_for_another_contract_admits_nothing(self):
        work = self.governed(predicate="signature", signing=True)
        sibling = work.repo / ".ai-native" / "work" / "easy"
        declared = self.trivial_contract(work)
        # A real, signed admission — for the *other* work's contract.
        work.admit(sibling, work.artifacts())
        with self.assertRaises(ControllerError) as refusal:
            WorkController(sibling).create(declared)
        self.assertIn("different initial contract", str(refusal.exception))

    def test_a97_a_properly_admitted_contract_is_created_and_converges(self):
        """The control: admission is a bar, not a wall."""

        work = self.governed(predicate="signature", signing=True)
        sibling = work.repo / ".ai-native" / "work" / "easy"
        declared = self.trivial_contract(work)
        work.admit(sibling, declared)
        self.assertEqual(1, WorkController(sibling).create(declared)["revision"])
        work.commit_governed_state()
        self.assertEqual("CONVERGED", evaluate_work(sibling, work.repo).verdict.verdict)


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required to exercise a real signature predicate")
class SignerAuthorizationTests(unittest.TestCase):
    """A98: a valid signature is not an authorization.

    Git answers whether a signature verifies against the configured keyring. It
    cannot answer whether that signer may approve a policy change here. Being
    able to sign ordinary commits is not being allowed to weaken the bar.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def weaker(self, work):
        (work.repo / "tests" / "easy.py").write_text("print('Ran 1 test in 0.0s'); print('OK')\n", encoding="utf-8")
        work.commit_governed_state()
        registry = work.registry()
        registry["commands"]["check"]["argv"] = [sys.executable, "tests/easy.py"]
        return {"command_registry": registry}

    def test_a98_a_valid_signature_by_an_unauthorized_signer_is_refused(self):
        work = self.governed(predicate="signature", signing=True)
        intruder = work.add_signer("intruder@example.invalid")
        self.assertNotIn(intruder.fingerprint, work.authorized_signers())
        work.use_signer(intruder)
        weaker = self.weaker(work)
        approval = work.record_approval_for_change(weaker)
        # Git verifies the commit: the key is in the allowed-signers file the
        # repository configures. The project never authorized this identity.
        self.assertEqual(intruder.fingerprint, signature_signers(work.repo, [str(approval.relative_to(work.repo)).replace("\\", "/")])[str(approval.relative_to(work.repo)).replace("\\", "/")])
        with self.assertRaises(ControllerError) as refusal:
            WorkController(work.work).mutate(1, weaker, approval=approval)
        self.assertIn("signature_verified", str(refusal.exception))
        self.assertEqual(1, WorkController(work.work).read()["revision"])

    def test_a98_the_authorized_signer_is_accepted(self):
        """The control, without which the case above proves only that nothing works."""

        work = self.governed(predicate="signature", signing=True)
        weaker = self.weaker(work)
        WorkController(work.work).mutate(1, weaker, approval=work.record_approval_for_change(weaker))
        self.assertEqual(2, WorkController(work.work).read()["revision"])

    def test_a98_widening_the_verifier_configuration_grants_no_authority(self):
        """The trusted signer set is pinned by the project, not by .git/config."""

        work = self.governed(predicate="signature", signing=True)
        # The actor adds its own key to the repository's allowed-signers file,
        # which is exactly the configuration Git consults.
        intruder = work.add_signer("intruder@example.invalid")
        work.use_signer(intruder)
        weaker = self.weaker(work)
        approval = work.record_approval_for_change(weaker)
        with self.assertRaises(ControllerError):
            WorkController(work.work).mutate(1, weaker, approval=approval)

    def test_a98_an_anchor_rewritten_to_authorize_the_actor_establishes_nothing(self):
        """Editing the pinned set is possible; making it stick is not."""

        work = self.governed(predicate="signature", signing=True)
        intruder = work.add_signer("intruder@example.invalid")
        anchor = json.loads(Path(work.anchor).read_text(encoding="utf-8"))
        anchor["authorized_signers"] = sorted(anchor["authorized_signers"] + [intruder.fingerprint])
        anchor["trust_digest"] = trust_commitment(anchor)
        Path(work.anchor).write_text(json.dumps(anchor), encoding="utf-8")
        work.use_signer(intruder)
        work.commit_governed_state()
        evaluation = evaluate_work(work.work, work.repo)
        self.assertEqual("INVALID", evaluation.verdict.verdict)
        self.assertIn("PROJECT_TRUST_UNVERIFIED", [gap.code for gap in evaluation.verdict.gaps])


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required to exercise a real signature predicate")
class MultiPathSignatureTests(unittest.TestCase):
    """A99: a set of objects is signed only when every object is."""

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def test_a99_one_signed_commit_does_not_sign_a_whole_path_set(self):
        work = self.governed(predicate="signature", signing=True)
        (work.repo / "src" / "unsigned.py").write_text("VALUE = 2\n", encoding="utf-8")
        git(work.repo, "add", "-A")
        git(work.repo, "commit", "-m", "unsigned", "--no-gpg-sign")
        (work.repo / "src" / "signed.py").write_text("VALUE = 3\n", encoding="utf-8")
        git(work.repo, "add", "-A")
        git(work.repo, "commit", "-m", "signed")
        authorized = work.authorized_signers()
        both = ["src/unsigned.py", "src/signed.py"]
        self.assertTrue(observe(work.repo, ["src/signed.py"], authorized_signers=authorized).signature_verified)
        self.assertFalse(observe(work.repo, ["src/unsigned.py"], authorized_signers=authorized).signature_verified)
        # The most recent commit touching either path is the signed one. The
        # answer for the set must still be no.
        self.assertFalse(observe(work.repo, both, authorized_signers=authorized).signature_verified)
        self.assertIsNone(signature_signers(work.repo, both)["src/unsigned.py"])

    def test_a99_a_fully_signed_path_set_is_verified(self):
        """The control."""

        work = self.governed(predicate="signature", signing=True)
        for name in ("first.py", "second.py"):
            (work.repo / "src" / name).write_text("VALUE = 1\n", encoding="utf-8")
            git(work.repo, "add", "-A")
            git(work.repo, "commit", "-m", f"signed {name}")
        self.assertTrue(observe(work.repo, ["src/first.py", "src/second.py"], authorized_signers=work.authorized_signers()).signature_verified)

    def test_a99_no_authorized_set_establishes_nothing(self):
        work = self.governed(predicate="signature", signing=True)
        self.assertFalse(observe(work.repo, ["src/app.py"]).signature_verified)
        self.assertFalse(observe(work.repo, ["src/app.py"], authorized_signers=[]).signature_verified)


class RootConnectivityTests(unittest.TestCase):
    """A100: a root that changes content must say what it replaces."""

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def test_a100_a_root_change_without_a_predecessor_is_refused(self):
        work = self.governed()
        orphan = dict(work.approval_root, root_provenance="SIGNED")
        orphan["root_digest"] = approval_root_commitment(orphan)
        self.assertNotIn("predecessor", orphan)
        changes = {"approval_root": orphan}
        with self.assertRaises(ControllerError) as refusal:
            WorkController(work.work).mutate(1, changes, approval=work.record_approval_for_change(changes))
        self.assertIn("predecessor", str(refusal.exception))

    def test_a100_a_predecessor_that_is_not_the_committed_root_is_refused(self):
        work = self.governed()
        stranger = dict(work.approval_root, uid=generate_uid("root"))
        stranger["root_digest"] = approval_root_commitment(stranger)
        successor = work.successor_root(stranger)
        changes = {"approval_root": successor}
        with self.assertRaises(ControllerError) as refusal:
            WorkController(work.work).mutate(1, changes, approval=work.record_approval_for_change(changes))
        self.assertIn("not the committed root", str(refusal.exception))

    def test_a100_a_predecessorless_root_is_not_a_second_genesis(self):
        """The chain terminates at the pinned genesis, not at any root."""

        work = self.governed()
        orphan = dict(work.approval_root, uid=generate_uid("root"), root_provenance="SIGNED")
        orphan["root_digest"] = approval_root_commitment(orphan)
        genesis = approval_root_commitment(work.approval_root)
        evidence = SimpleEvidence(orphan, work.commitment)
        verdict = evaluate_trust(evidence, policy=work.policy, approval_root=orphan, evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED, genesis_digest=genesis)
        self.assertEqual("ROOT_OF_TRUST_INVALID", verdict.code)

    def test_a100_a_proper_rotation_is_accepted_and_converges(self):
        """The control: legitimate rotation must remain possible."""

        work = self.governed()
        _, committed = WorkController(work.work).load_committed_artifacts()
        rotated = work.successor_root(committed["approval_root"])
        changes = {"approval_root": rotated}
        WorkController(work.work).mutate(1, changes, approval=work.record_approval_for_change(changes))
        work.commit_governed_state()
        self.assertEqual([work.approval_root["uid"], rotated["uid"]], [entry["uid"] for entry in WorkController(work.work).root_history()])
        self.assertEqual("CONVERGED", evaluate_work(work.work, work.repo).verdict.verdict)


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required to exercise a real signature predicate")
class BootstrapTrustBoundaryTests(unittest.TestCase):
    """A101: where the Work Plane's self-verification stops.

    This case does not assert a defence. It asserts a *boundary*, and it exists
    so that the boundary is executable rather than only written down.

    A root of trust cannot prove its own legitimacy from data whose authority
    comes from that root. Before a trusted anchor exists, an actor able to run
    commands and commit can generate a key, configure Git to verify it, name
    its own fingerprint as authorized, and sign the anchor. Every later check
    then passes truthfully -- and all of them descend from that one actor.

    ADR-0006 takes the explicit decision: establishing the first anchor is a
    privileged ceremony inside the trusted computing base, and a controlled
    agent must not be given authority to perform it. If that assumption is ever
    replaced by an external trust source, this test must fail and be rewritten.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def test_a101_a_self_bootstrapped_project_converges_and_that_is_the_boundary(self):
        # The fixture performs exactly the attack protocol: one actor generates
        # the key, configures the verifier, chooses the authorized set, signs
        # the anchor, admits the work and runs the verification.
        work = self.governed(predicate="signature", signing=True)
        anchor = json.loads(Path(work.anchor).read_text(encoding="utf-8"))
        self.assertEqual([work.signing_key.fingerprint], anchor["authorized_signers"])
        self.assertIsNone(anchor_refusal(work.anchor, anchor))
        self.assertEqual("CONVERGED", evaluate_work(work.work, work.repo).verdict.verdict)

    def test_a101_the_runtime_makes_no_claim_about_who_performed_genesis(self):
        """Nothing recorded distinguishes a trusted operator from the actor."""

        work = self.governed(predicate="signature", signing=True)
        anchor = json.loads(Path(work.anchor).read_text(encoding="utf-8"))
        # `initialized_by` is a string the caller supplied. It is metadata, and
        # the engine must never be read as having verified it.
        self.assertEqual("project-owner", anchor["bootstrap"]["initialized_by"])
        self.assertNotIn("initialized_by", str(anchor_refusal(work.anchor, anchor)))
        # What the runtime does establish, it establishes only after genesis.
        self.assertEqual(1, len(anchor["authorized_signers"]))


class PolicyEvolutionTests(unittest.TestCase):
    """A102: a transition is judged under the policy that authorized it.

    ADR-0004 said the anchor deliberately does not pin the policy, because
    policy evolves through authorized mutation. The chain walk did not support
    that: it required every historical root to carry the *current* policy
    commitment, so an evolved project could never validate its own genesis.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def test_a102_an_authorized_policy_change_still_converges(self):
        """The control, and the finding: this was unreachable before."""

        work = self.governed()
        _, committed = WorkController(work.work).load_committed_artifacts()
        evolved, commitment = work.evolved_policy(promotion_policy="explicit-v2")
        successor = work.successor_root(committed["approval_root"], policy_digest=commitment)
        changes = {"project_policy": evolved, "approval_root": successor}
        WorkController(work.work).mutate(1, changes, approval=work.record_approval_for_change(changes))
        work.commit_governed_state()
        controller = WorkController(work.work)
        self.assertEqual(2, len(controller.policy_history()))
        self.assertEqual(2, len(controller.root_history()))
        evaluation = evaluate_work(work.work, work.repo)
        self.assertEqual("CONVERGED", evaluation.verdict.verdict, [gap.code for gap in evaluation.verdict.gaps])

    def test_a102_a_later_weaker_policy_does_not_authorize_an_old_transition(self):
        work = self.governed()
        genesis = work.approval_root
        strict, strict_commitment = work.evolved_policy()
        weak, weak_commitment = work.evolved_policy(promotion_policy="anything-goes")
        weak["approval_predicate"] = dict(weak["approval_predicate"], predicate_id="recorded_owner_ack")
        weak_commitment = policy_commitment(weak)
        for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
            weak[field] = dict(weak[field], policy_digest=weak_commitment)
        parent = dict(genesis, policy_digest=strict_commitment)
        parent["root_digest"] = approval_root_commitment(parent)

        def successor(predicate_id, policy_digest):
            child = dict(parent, uid=generate_uid("root"), policy_digest=weak_commitment)
            child["predecessor"] = {"uid": parent["uid"], "digest": parent["root_digest"]}
            child["transition_approval"] = {
                "predicate_id": predicate_id, "approved_by": "someone", "provenance": "GIT_RECORDED",
                "successor_uid": child["uid"], "predecessor_digest": parent["root_digest"],
                "successor_commitment": DIGEST, "policy_digest": policy_digest,
            }
            child["root_digest"] = DIGEST
            child["transition_approval"]["successor_commitment"] = successor_commitment(child)
            child["root_digest"] = approval_root_commitment(child)
            return child

        # The transition is issued under the *later*, weaker policy: its own
        # predicate and its own commitment. The predecessor never saw it.
        retroactive = successor(weak["approval_predicate"]["predicate_id"], weak_commitment)
        verdict = evaluate_trust(
            SimpleEvidence(retroactive, weak_commitment), policy=weak, approval_root=retroactive,
            approval_chain=[parent], policy_chain=[strict, weak],
            evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED,
            genesis_digest=approval_root_commitment(parent),
        )
        self.assertEqual("ROOT_OF_TRUST_INVALID", verdict.code)

        # The control: the same rotation, authorized by the predecessor.
        authorized = successor(strict["approval_predicate"]["predicate_id"], strict_commitment)
        verdict = evaluate_trust(
            SimpleEvidence(authorized, weak_commitment), policy=weak, approval_root=authorized,
            approval_chain=[parent], policy_chain=[strict, weak],
            evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED,
            genesis_digest=approval_root_commitment(parent),
        )
        self.assertEqual("TRUSTED", verdict.code)

    def test_a102_a_policy_that_was_never_committed_authorizes_nothing(self):
        """History is resolved from the committed chain, not from the argument."""

        work = self.governed()
        strict, strict_commitment = work.evolved_policy()
        parent = dict(work.approval_root, policy_digest=strict_commitment)
        parent["root_digest"] = approval_root_commitment(parent)
        verdict = evaluate_trust(
            SimpleEvidence(parent, strict_commitment), policy=strict, approval_root=parent,
            approval_chain=[], policy_chain=[], evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED,
            genesis_digest=approval_root_commitment(parent),
        )
        self.assertEqual("TRUSTED", verdict.code)


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required to exercise a real signature predicate")
class ControllerAnchorVerificationTests(unittest.TestCase):
    """A103: the sole normative writer refuses an anchor it already knows is bad."""

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def rewrite_anchor(self, work, extra):
        anchor = json.loads(Path(work.anchor).read_text(encoding="utf-8"))
        anchor["authorized_signers"] = sorted(anchor["authorized_signers"] + [extra])
        anchor["trust_digest"] = trust_commitment(anchor)
        Path(work.anchor).write_text(json.dumps(anchor), encoding="utf-8")
        work.commit_governed_state()
        return anchor

    def test_a103_an_invalid_anchor_cannot_authorize_a_write(self):
        work = self.governed(predicate="signature", signing=True)
        intruder = work.add_signer("intruder@example.invalid")
        anchor = self.rewrite_anchor(work, intruder.fingerprint)
        # The evaluator already refuses this anchor. The writer must too.
        self.assertIsNotNone(anchor_refusal(work.anchor, anchor))
        work.use_signer(intruder)
        (work.repo / "tests" / "easy.py").write_text("print('Ran 1 test in 0.0s'); print('OK')\n", encoding="utf-8")
        work.commit_governed_state()
        registry = work.registry()
        registry["commands"]["check"]["argv"] = [sys.executable, "tests/easy.py"]
        weaker = {"command_registry": registry}
        approval = work.record_approval_for_change(weaker)
        with self.assertRaises(ControllerError) as refusal:
            WorkController(work.work).mutate(1, weaker, approval=approval)
        self.assertIn("UNGOVERNED_PROJECT", str(refusal.exception))
        self.assertEqual(1, WorkController(work.work).read()["revision"])

    def test_a103_an_invalid_anchor_cannot_admit_a_new_work(self):
        work = self.governed(predicate="signature", signing=True)
        intruder = work.add_signer("intruder@example.invalid")
        self.rewrite_anchor(work, intruder.fingerprint)
        sibling = work.repo / ".ai-native" / "work" / "w2"
        declared = work.artifacts()
        work.admit(sibling, declared)
        with self.assertRaises(ControllerError) as refusal:
            WorkController(sibling).create(declared)
        self.assertIn("UNGOVERNED_PROJECT", str(refusal.exception))

    def test_a103_a_valid_anchor_still_authorizes_writes(self):
        """The control."""

        work = self.governed(predicate="signature", signing=True)
        (work.repo / "tests" / "easy.py").write_text("print('Ran 1 test in 0.0s'); print('OK')\n", encoding="utf-8")
        work.commit_governed_state()
        registry = work.registry()
        registry["commands"]["check"]["argv"] = [sys.executable, "tests/easy.py"]
        weaker = {"command_registry": registry}
        WorkController(work.work).mutate(1, weaker, approval=work.record_approval_for_change(weaker))
        self.assertEqual(2, WorkController(work.work).read()["revision"])


class PolicyRootAtomicityTests(unittest.TestCase):
    """A104: a root must commit to the policy it is written with, and move with it.

    The evaluator requires the current root to carry the current policy
    commitment, so a revision where they disagree can never be authority. Round
    6 left the writer able to commit exactly that.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def test_a104_a_policy_only_mutation_is_refused(self):
        work = self.governed()
        evolved, _ = work.evolved_policy(promotion_policy="explicit-v2")
        changes = {"project_policy": evolved}
        with self.assertRaises(ControllerError) as refusal:
            WorkController(work.work).mutate(1, changes, approval=work.record_approval_for_change(changes))
        self.assertIn("rotate the root in the same mutation", str(refusal.exception))
        self.assertEqual(1, WorkController(work.work).read()["revision"])

    def test_a104_a_root_that_commits_to_another_policy_is_refused(self):
        work = self.governed()
        _, committed = WorkController(work.work).load_committed_artifacts()
        evolved, commitment = work.evolved_policy(promotion_policy="explicit-v2")
        # The root rotates, properly, but still commits to the policy being left.
        stale = work.successor_root(committed["approval_root"])
        changes = {"project_policy": evolved, "approval_root": stale}
        with self.assertRaises(ControllerError) as refusal:
            WorkController(work.work).mutate(1, changes, approval=work.record_approval_for_change(changes))
        self.assertIn("does not commit to the policy", str(refusal.exception))

    def test_a104_a_root_committing_to_an_unrelated_policy_is_refused(self):
        work = self.governed()
        _, committed = WorkController(work.work).load_committed_artifacts()
        _, other = work.evolved_policy(promotion_policy="somewhere-else")
        drifting = work.successor_root(committed["approval_root"], policy_digest=other)
        changes = {"approval_root": drifting}  # the policy itself is unchanged
        with self.assertRaises(ControllerError) as refusal:
            WorkController(work.work).mutate(1, changes, approval=work.record_approval_for_change(changes))
        self.assertIn("does not commit to the policy", str(refusal.exception))

    def test_a104_policy_and_root_moving_together_is_accepted(self):
        """The control: evolution must remain possible in one approved mutation."""

        work = self.governed()
        _, committed = WorkController(work.work).load_committed_artifacts()
        evolved, commitment = work.evolved_policy(promotion_policy="explicit-v2")
        successor = work.successor_root(committed["approval_root"], policy_digest=commitment)
        changes = {"project_policy": evolved, "approval_root": successor}
        WorkController(work.work).mutate(1, changes, approval=work.record_approval_for_change(changes))
        work.commit_governed_state()
        self.assertEqual("CONVERGED", evaluate_work(work.work, work.repo).verdict.verdict)


class HistoricalTransitionEvidenceTests(unittest.TestCase):
    """A105: a transition is judged by the evidence bound to it.

    The chain walker used one observation of the *current* authority for every
    historical transition, so it asked "does today's authority satisfy the
    historical predicate" rather than "did this transition have the property
    when it was authorized". Those are different questions.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def chain(self, work):
        """A committed rotation, plus the pieces needed to judge it directly."""

        _, committed = WorkController(work.work).load_committed_artifacts()
        parent = committed["approval_root"]
        successor = work.successor_root(parent)
        changes = {"approval_root": successor}
        WorkController(work.work).mutate(1, changes, approval=work.record_approval_for_change(changes))
        work.commit_governed_state()
        return parent, successor

    def test_a105_the_commit_marker_records_what_authorized_each_transition(self):
        work = self.governed()
        _, successor = self.chain(work)
        transitions = WorkController(work.work).root_transitions()
        self.assertIn(successor["uid"], transitions)
        evidence = transitions[successor["uid"]]
        self.assertEqual(40, len(evidence["commit"]))
        self.assertEqual(64, len(evidence["approval_digest"]))
        # The genesis root authorized nothing inside this work.
        self.assertEqual(1, len(transitions))

    def test_a105_current_authority_cannot_supply_historical_facts(self):
        work = self.governed()
        parent, successor = self.chain(work)
        unsigned = ProvenanceFacts(git_recorded=True, signature_verified=False, local_dirty=False)
        strict, commitment = work.evolved_policy()
        strict["approval_predicate"] = dict(strict["approval_predicate"], predicate_id="signature")
        commitment = policy_commitment(strict)
        for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
            strict[field] = dict(strict[field], policy_digest=commitment)
        parent = dict(parent, policy_digest=commitment)
        parent["root_digest"] = approval_root_commitment(parent)
        rebuilt = work.successor_root(parent, policy_digest=commitment, predicate_id="signature", transition_policy_digest=commitment)

        def verdict(bound):
            return evaluate_trust(
                SimpleEvidence(rebuilt, commitment), policy=strict, approval_root=rebuilt,
                approval_chain=[parent], policy_chain=[strict],
                evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED,
                genesis_digest=approval_root_commitment(parent),
                transition_facts=bound,
            ).code

        # The authority observed *now* is signed. The transition's own evidence
        # is not. The transition must stay invalid.
        self.assertEqual("ROOT_OF_TRUST_INVALID", verdict({rebuilt["uid"]: unsigned}))
        # A transition with no bound evidence at all is not a transition anyone
        # can check.
        self.assertEqual("ROOT_OF_TRUST_INVALID", verdict({}))
        # The control: evidence bound to the transition, satisfying it.
        self.assertEqual("TRUSTED", verdict({rebuilt["uid"]: ESTABLISHED}))

    def test_a105_a_committed_rotation_still_converges(self):
        """The control, end to end: the bound evidence is real and it validates."""

        work = self.governed()
        self.chain(work)
        evaluation = evaluate_work(work.work, work.repo)
        self.assertEqual("CONVERGED", evaluation.verdict.verdict, [gap.code for gap in evaluation.verdict.gaps])


class ApprovalReplayTests(unittest.TestCase):
    """A106: an approval authorizes one transition, not one destination.

    An approval named only the state being reached, so an old one could be
    replayed later to undo a strengthening that happened since. Reproduced
    before the fix: revision 1 approved a weak registry, revision 3 restored
    the strong one, and replaying the revision-1 approval reached revision 4
    with the weak registry back.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def weak(self, work):
        (work.repo / "tests" / "easy.py").write_text("print('Ran 1 test in 0.0s'); print('OK')\n", encoding="utf-8")
        work.commit_governed_state()
        registry = work.registry()
        registry["commands"]["check"]["argv"] = [sys.executable, "tests/easy.py"]
        return {"command_registry": registry}

    def test_a106_an_old_approval_cannot_undo_a_later_strengthening(self):
        work = self.governed()
        weak = self.weak(work)
        approval = work.record_approval_for_change(weak)
        WorkController(work.work).mutate(1, weak, approval=approval)
        work.commit_governed_state()

        # A third state, stricter than either: not a return to revision 1, so the
        # base the old approval was issued against is genuinely gone.
        stricter = work.registry()
        stricter["commands"]["check"]["timeout_seconds"] = 10
        strong = {"command_registry": stricter}
        WorkController(work.work).mutate(2, strong, approval=work.record_approval_for_change(strong))
        work.commit_governed_state()

        with self.assertRaises(ControllerError) as refusal:
            WorkController(work.work).mutate(3, weak, approval=approval)
        self.assertIn("different state than the one being changed", str(refusal.exception))
        _, committed = WorkController(work.work).load_committed_artifacts()
        self.assertEqual("tests/check.py", committed["command_registry"]["commands"]["check"]["argv"][1])

    def test_a106_an_approval_issued_against_the_current_state_is_accepted(self):
        """The control: the same weakening, approved now, still goes through."""

        work = self.governed()
        weak = self.weak(work)
        WorkController(work.work).mutate(1, weak, approval=work.record_approval_for_change(weak))
        self.assertEqual(2, WorkController(work.work).read()["revision"])


class TransitionApprovalBindingTests(unittest.TestCase):
    """A107: the recorded approval digest must be checked, not merely recorded.

    Round 7 bound each transition to the commit that carried its approval, and
    recorded that approval's digest beside it -- then never read the digest
    back. A commit signature says something was signed; it does not say what.
    """

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def rotated(self, work):
        _, committed = WorkController(work.work).load_committed_artifacts()
        successor = work.successor_root(committed["approval_root"])
        changes = {"approval_root": successor}
        WorkController(work.work).mutate(1, changes, approval=work.record_approval_for_change(changes))
        work.commit_governed_state()
        return successor

    def rewrite_authority(self, work, **changes):
        """Edit what the commit marker claims authorized the rotation."""

        path = work.work / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for entry in manifest["root_chain"]:
            if "authority" in entry:
                entry["authority"] = {**entry["authority"], **changes}
        path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        work.commit_governed_state()

    def refusals(self, work):
        """Every reason the evaluation gives, gaps and per-evidence alike.

        A broken chain surfaces as `ROOT_OF_TRUST_INVALID` inside the reasons
        an individual run was ruled ineligible for, not as a standalone gap.
        See the round-8 packet: the classification is worth a look, and this
        round deliberately does not change it.
        """

        evaluation = evaluate_work(work.work, work.repo)
        self.assertNotEqual("CONVERGED", evaluation.verdict.verdict)
        reasons = [gap.code for gap in evaluation.verdict.gaps]
        for assessment in evaluation.assessments:
            reasons.extend(assessment.reasons)
        return reasons

    def test_a107_the_commit_marker_records_commit_path_and_digest(self):
        work = self.governed()
        successor = self.rotated(work)
        evidence = WorkController(work.work).root_transitions()[successor["uid"]]
        self.assertEqual({"commit", "approval_path", "approval_digest"}, set(evidence))
        self.assertTrue(evidence["approval_path"].startswith(".ai-native/"))

    def test_a107_a_digest_naming_another_object_invalidates_the_chain(self):
        work = self.governed()
        self.rotated(work)
        self.assertEqual("CONVERGED", evaluate_work(work.work, work.repo).verdict.verdict)
        # The commit is real and signed exactly as before. Only the claim about
        # what it contained is false.
        self.rewrite_authority(work, approval_digest="b" * 64)
        self.assertIn("ROOT_OF_TRUST_INVALID", self.refusals(work))

    def test_a107_a_path_the_commit_does_not_hold_invalidates_the_chain(self):
        work = self.governed()
        self.rotated(work)
        self.rewrite_authority(work, approval_path="src/app.py")
        self.assertIn("ROOT_OF_TRUST_INVALID", self.refusals(work))

    def test_a107_a_working_tree_approval_cannot_stand_in_for_the_commit(self):
        """What is on disk now is not what the commit contained."""

        work = self.governed()
        successor = self.rotated(work)
        evidence = WorkController(work.work).root_transitions()[successor["uid"]]
        approved = work.repo / evidence["approval_path"]
        self.assertTrue(approved.is_file())
        # Point the chain at a commit that predates the approval entirely. The
        # file is still there in the working tree; the commit does not hold it.
        first = subprocess.run(["git", "-C", str(work.repo), "rev-list", "--max-parents=0", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        self.rewrite_authority(work, commit=first)
        self.assertIn("ROOT_OF_TRUST_INVALID", self.refusals(work))

    def test_a107_a_matching_commit_path_and_digest_stay_valid(self):
        """The control."""

        work = self.governed()
        self.rotated(work)
        evaluation = evaluate_work(work.work, work.repo)
        self.assertEqual("CONVERGED", evaluation.verdict.verdict, [gap.code for gap in evaluation.verdict.gaps])


if __name__ == "__main__":
    unittest.main()
