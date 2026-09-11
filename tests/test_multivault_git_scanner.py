import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.multivault.git_scanner import CandidateObjectScanner, ScanVerdict


def run_git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True)
    if check and result.returncode:
        raise AssertionError(f"git {' '.join(arguments)} failed: {result.stderr.decode('utf-8', 'replace')}")
    return result


def commit_file(root: Path, relative: str, content: bytes, message: str = "change") -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    run_git(root, "add", "--", relative)
    run_git(root, "-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-q", "-m", message)
    return run_git(root, "rev-parse", "HEAD").stdout.strip().decode()


class CandidateObjectScannerTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self._temporary.name) / "repo"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "checkout", "-q", "-b", "main")
        self.base = commit_file(self.repo, "README.md", b"base\n", "base")

    def tearDown(self):
        self._temporary.cleanup()

    def scan(self, source: str, **scanner_options):
        scanner = CandidateObjectScanner(self.repo, **scanner_options)
        return scanner.scan(source_oid=source, remote_base_oid=self.base, refspec=f"{source}:refs/heads/main")

    def test_candidate_set_excludes_base_objects(self):
        source = commit_file(self.repo, "notes/clean.txt", b"clean\n")
        result = self.scan(source)
        self.assertEqual(ScanVerdict.PASS, result.verdict)
        self.assertEqual(1, result.blobs_scanned)

    def test_secret_in_new_blob_is_a_leak(self):
        source = commit_file(self.repo, "config.txt", b"token = ghp_abcdefghijklmnop\n")
        result = self.scan(source)
        self.assertEqual(ScanVerdict.LEAK, result.verdict)
        self.assertIn("secret", [finding.category for finding in result.findings])

    def test_forbidden_path_is_a_leak(self):
        source = commit_file(self.repo, "secrets/canary.txt", b"not-a-secret\n")
        result = self.scan(source, forbidden_paths=("secrets/*",))
        self.assertEqual(ScanVerdict.LEAK, result.verdict)
        self.assertIn("forbidden_path", [finding.category for finding in result.findings])

    def test_large_binary_is_a_leak(self):
        source = commit_file(self.repo, "asset.bin", b"\x00" * 64)
        result = self.scan(source, max_binary_bytes=16)
        self.assertEqual(ScanVerdict.LEAK, result.verdict)
        self.assertIn("large_binary", [finding.category for finding in result.findings])

    def test_lfs_pointer_is_a_leak(self):
        pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 12\n"
        source = commit_file(self.repo, "big.bin", pointer)
        result = self.scan(source)
        self.assertEqual(ScanVerdict.LEAK, result.verdict)
        self.assertIn("lfs_pointer", [finding.category for finding in result.findings])

    def test_missing_source_object_is_incomplete(self):
        unknown = "f" * 40
        scanner = CandidateObjectScanner(self.repo)
        result = scanner.scan(source_oid=unknown, remote_base_oid=self.base, refspec=f"{unknown}:refs/heads/main")
        self.assertEqual(ScanVerdict.INCOMPLETE, result.verdict)

    def test_refspec_source_mismatch_is_incomplete(self):
        source = commit_file(self.repo, "clean.txt", b"clean\n")
        scanner = CandidateObjectScanner(self.repo)
        result = scanner.scan(source_oid=source, remote_base_oid=self.base, refspec=f"{self.base}:refs/heads/main")
        self.assertEqual(ScanVerdict.INCOMPLETE, result.verdict)

    def test_unreadable_repository_is_incomplete(self):
        scanner = CandidateObjectScanner(self.repo / "missing")
        result = scanner.scan(source_oid=self.base, remote_base_oid=None, refspec="main:refs/heads/main")
        self.assertEqual(ScanVerdict.INCOMPLETE, result.verdict)

    def test_promisor_configuration_is_incomplete(self):
        run_git(self.repo, "config", "remote.origin.promisor", "true")
        source = commit_file(self.repo, "clean.txt", b"clean\n")
        result = self.scan(source)
        self.assertEqual(ScanVerdict.INCOMPLETE, result.verdict)

    def test_shallow_repository_is_incomplete(self):
        target = Path(tempfile.mkdtemp(prefix="mv16-shallow-"))
        try:
            clone = subprocess.run(
                ["git", "clone", "-q", "--no-local", "--depth", "1", self.repo.resolve().as_uri(), str(target)],
                capture_output=True,
            )
            if clone.returncode:
                self.skipTest("git shallow clone is unavailable in this environment")
            head = run_git(target, "rev-parse", "HEAD").stdout.strip().decode()
            scanner = CandidateObjectScanner(target)
            result = scanner.scan(source_oid=head, remote_base_oid=None, refspec=f"{head}:refs/heads/main")
            self.assertEqual(ScanVerdict.INCOMPLETE, result.verdict)
        finally:
            shutil.rmtree(target, ignore_errors=True)

    def test_scan_without_base_covers_the_whole_reachable_set(self):
        source = commit_file(self.repo, "notes/clean.txt", b"clean\n")
        scanner = CandidateObjectScanner(self.repo)
        result = scanner.scan(source_oid=source, remote_base_oid=None, refspec=f"{source}:refs/heads/main")
        self.assertEqual(ScanVerdict.PASS, result.verdict)
        self.assertEqual(2, result.blobs_scanned)

    def test_scan_is_deterministic(self):
        source = commit_file(self.repo, "clean.txt", b"clean\n")
        first = self.scan(source)
        second = self.scan(source)
        self.assertEqual(first, second)