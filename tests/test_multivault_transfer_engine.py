import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.multivault.git_authority import (
    ApprovedGitRemote,
    GitTransportPolicy,
    ObservedRepositoryIdentity,
    ObservedTransport,
    Visibility,
)
from ainative.multivault.push_guard import GovernedPushAuthority, PushAuthorization
from ainative.multivault.schema import SecurityClassification
from ainative.multivault.transfer_engine import (
    FETCH_DESTINATION_DENIED,
    FETCH_FAILED,
    FORCE_PUSH_DENIED,
    LFS_NETWORK_DENIED,
    PUSH_DESTINATION_DENIED,
    PUSH_LOCK_HELD,
    PUSH_SCAN_LEAK,
    REF_DELETION_DENIED,
    SECONDARY_NETWORK_DENIED,
    GovernedTransferEngine,
    PushPreparation,
)


def run_git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True)
    if check and result.returncode:
        raise AssertionError(f"git {' '.join(arguments)} failed: {result.stderr.decode('utf-8', 'replace')}")
    return result


def commit_file(root: Path, relative: str, content: bytes, message: str = "change") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    run_git(root, "add", "--", relative)
    run_git(root, "-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-q", "-m", message)


def build_fixture(tmp: Path):
    origin = tmp / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], capture_output=True, check=True)
    seed = tmp / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], capture_output=True, check=True)
    run_git(seed, "checkout", "-q", "-b", "main")
    commit_file(seed, "README.md", b"base\n", "base")
    run_git(seed, "push", "-q", "origin", "main")
    run_git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    work = tmp / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], capture_output=True, check=True)
    return origin, work, seed


def approved_remote(url: str) -> ApprovedGitRemote:
    return ApprovedGitRemote(
        canonical_fetch_url=url,
        canonical_push_url=url,
        provider_type="local",
        stable_repository_id="repo-1",
        required_owner_org="company",
        required_visibility_for_push=Visibility.PRIVATE,
        allowed_refs=("refs/heads/*",),
    )


def transport_policy() -> GitTransportPolicy:
    return GitTransportPolicy(
        protocol_allowlist=("file",),
        transport_executable_identity="git-local",
        proxy=None,
        ssh_command=None,
        credential_helper=None,
        ssh_peer_policy="not-applicable",
        tls_peer_policy="not-applicable",
        effective_transport_config_digest="transport-digest",
    )


def observed_remote(url: str, **overrides) -> ObservedRepositoryIdentity:
    fields = {
        "provider_type": "local",
        "stable_repository_id": "repo-1",
        "owner_org": "company",
        "visibility": Visibility.PRIVATE,
        "effective_fetch_url": url,
        "effective_push_url": url,
    }
    fields.update(overrides)
    return ObservedRepositoryIdentity(**fields)


def observed_transport(**overrides) -> ObservedTransport:
    fields = {
        "protocol": "file",
        "transport_executable_identity": "git-local",
        "proxy": None,
        "ssh_command": None,
        "credential_helper": None,
        "effective_transport_config_digest": "transport-digest",
    }
    fields.update(overrides)
    return ObservedTransport(**fields)


class TransferEngineTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.tmp = Path(self._temporary.name)
        self.origin, self.work, self.seed = build_fixture(self.tmp)
        self.url = self.origin.as_uri()

    def tearDown(self):
        self._temporary.cleanup()

    def engine(self, *, url=None, classification=SecurityClassification.CONFIDENTIAL) -> GovernedTransferEngine:
        remote_url = url or self.url
        return GovernedTransferEngine(
            self.work,
            approved_remote=approved_remote(remote_url),
            transport_policy=transport_policy(),
            push_authority=GovernedPushAuthority("company-a", "checkout-a"),
            classification=classification,
        )

    def fetch(self, engine, *, url=None, refs=("refs/heads/main",), observed=None, transport=None):
        remote_url = url or self.url
        return engine.fetch(
            requested_refs=refs,
            observed_remote=observed if observed is not None else observed_remote(remote_url),
            observed_transport=transport if transport is not None else observed_transport(),
            verified_at="2026-09-11T12:00:00Z",
        )

    def begin_push(self, engine, *, refspec="refs/heads/main:refs/heads/main", observed=None, transport=None):
        source = run_git(self.work, "rev-parse", "HEAD").stdout.strip().decode()
        base = run_git(self.work, "rev-parse", "refs/remotes/origin/main").stdout.strip().decode()
        return engine.begin_push(
            source_oid=source,
            expected_remote_base_oid=base,
            target_ref="refs/heads/main",
            exact_refspec=refspec,
            observed_remote=observed if observed is not None else observed_remote(self.url),
            observed_transport=transport if transport is not None else observed_transport(),
            expected_git_identity="Rwanbt <barat.erwan@gmail.com>",
        )

    def test_governed_fetch_records_evidence_and_state(self):
        commit_file(self.seed, "second.txt", b"second\n", "second")
        run_git(self.seed, "push", "-q", "origin", "main")
        outcome = self.fetch(self.engine())
        self.assertEqual("ALLOW", outcome.decision)
        self.assertIsNotNone(outcome.evidence)
        self.assertIsNotNone(outcome.repository_state)
        fetched = (self.work / ".git" / "FETCH_HEAD").read_text(encoding="utf-8")
        self.assertIn(run_git(self.seed, "rev-parse", "HEAD").stdout.strip().decode(), fetched)

    def test_fetch_denied_on_destination_identity_mismatch(self):
        outcome = self.fetch(self.engine(), observed=observed_remote(self.url, stable_repository_id="other"))
        self.assertEqual("DENY", outcome.decision)
        self.assertEqual(FETCH_DESTINATION_DENIED, outcome.code)

    def test_fetch_denied_on_transport_mismatch(self):
        outcome = self.fetch(self.engine(), transport=observed_transport(proxy="http://proxy.example"))
        self.assertEqual("DENY", outcome.decision)
        self.assertEqual(FETCH_DESTINATION_DENIED, outcome.code)

    def test_sensitive_fetch_denies_lfs_and_promisor_configuration(self):
        run_git(self.work, "config", "lfs.url", "https://lfs.example/repo")
        lfs = self.fetch(self.engine())
        self.assertEqual(LFS_NETWORK_DENIED, lfs.code)
        run_git(self.work, "config", "--unset", "lfs.url")
        run_git(self.work, "config", "remote.origin.promisor", "true")
        promisor = self.fetch(self.engine())
        self.assertEqual(SECONDARY_NETWORK_DENIED, promisor.code)

    def test_fetch_failure_is_reported(self):
        missing = (self.tmp / "missing.git").as_uri()
        outcome = self.fetch(self.engine(url=missing), url=missing)
        self.assertEqual("DENY", outcome.decision)
        self.assertEqual(FETCH_FAILED, outcome.code)

    def test_governed_push_completes_and_updates_the_remote(self):
        commit_file(self.work, "feature.txt", b"feature\n")
        preparation = self.begin_push(self.engine())
        self.assertIsInstance(preparation, PushPreparation)
        outcome = preparation.execute()
        self.assertEqual("ALLOW", outcome.decision)
        source = run_git(self.work, "rev-parse", "HEAD").stdout.strip().decode()
        origin_head = run_git(self.origin, "rev-parse", "refs/heads/main").stdout.strip().decode()
        self.assertEqual(source, origin_head)

    def test_push_capability_is_consumed_after_completion(self):
        commit_file(self.work, "feature.txt", b"feature\n")
        engine = self.engine()
        preparation = self.begin_push(engine)
        self.assertEqual("ALLOW", preparation.execute().decision)
        replay = engine._push_authority.authorize(preparation.capability, preparation.stdin_text)
        self.assertEqual("DENY", replay.decision)

    def test_force_and_deletion_refspecs_are_denied(self):
        commit_file(self.work, "feature.txt", b"feature\n")
        force = self.begin_push(self.engine(), refspec="+refs/heads/main:refs/heads/main")
        self.assertEqual(FORCE_PUSH_DENIED, force.code)
        deletion = self.begin_push(self.engine(), refspec=":refs/heads/main")
        self.assertEqual(REF_DELETION_DENIED, deletion.code)

    def test_push_scan_leak_is_denied_before_any_transfer(self):
        commit_file(self.work, "secret.txt", b"token = ghp_abcdefghijklmnop\n")
        outcome = self.begin_push(self.engine())
        self.assertEqual("DENY", outcome.decision)
        self.assertEqual(PUSH_SCAN_LEAK, outcome.code)
        origin_head = run_git(self.origin, "rev-parse", "refs/heads/main").stdout.strip().decode()
        self.assertNotEqual(run_git(self.work, "rev-parse", "HEAD").stdout.strip().decode(), origin_head)

    def test_push_lock_is_held_and_released(self):
        commit_file(self.work, "feature.txt", b"feature\n")
        first = self.begin_push(self.engine())
        self.assertIsInstance(first, PushPreparation)
        blocked = self.begin_push(self.engine())
        self.assertEqual(PUSH_LOCK_HELD, blocked.code)
        first.abort()
        released = self.begin_push(self.engine())
        self.assertIsInstance(released, PushPreparation)
        released.abort()

    def test_destination_denial_leaves_no_lock(self):
        commit_file(self.work, "feature.txt", b"feature\n")
        outcome = self.begin_push(self.engine(), observed=observed_remote(self.url, stable_repository_id="other"))
        self.assertEqual(PUSH_DESTINATION_DENIED, outcome.code)
        self.assertFalse((self.work / ".git" / "ainative-push.lock").exists())

    def test_denied_authorization_releases_the_lock(self):
        commit_file(self.work, "feature.txt", b"feature\n")
        preparation = self.begin_push(self.engine())
        outcome = preparation.execute(authorize=lambda capability, stdin: PushAuthorization("DENY", "AINATIVE_PUSH_REFS_MISMATCH", "forced"))
        self.assertEqual("DENY", outcome.decision)
        self.assertFalse((self.work / ".git" / "ainative-push.lock").exists())
        origin_head = run_git(self.origin, "rev-parse", "refs/heads/main").stdout.strip().decode()
        self.assertNotEqual(run_git(self.work, "rev-parse", "HEAD").stdout.strip().decode(), origin_head)

    def test_sensitive_push_denies_lfs_configuration(self):
        commit_file(self.work, "feature.txt", b"feature\n")
        run_git(self.work, "config", "filter.lfs.clean", "git-lfs clean -- %f")
        outcome = self.begin_push(self.engine())
        self.assertEqual(LFS_NETWORK_DENIED, outcome.code)