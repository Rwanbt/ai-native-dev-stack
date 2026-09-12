"""test_scan_code_execution.py — run_scanner argv, shell and parser contracts.

The scanner used to run `subprocess.run(cmd.split(), shell=(" " in cmd))` — a
shell for every real command — and the clippy parser read `line_start` as a
mapping while clippy emits an integer, so an AttributeError was swallowed by
the broad except and every clippy finding degraded to a warning (#127).

These tests pin the native argv, `shell=False`, the cwd and timeout, the
degradation paths, realistic clippy JSON fixtures, and one real-process smoke
test whenever ruff is available.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).parent.parent / "skills" / "debt-scan" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("scan_code", TOOLS / "scan_code.py")
scan_code = importlib.util.module_from_spec(_spec)
sys.modules["scan_code"] = scan_code
_spec.loader.exec_module(scan_code)

SCANNER_ARGS = {
    "ruff": ("ruff", "check", "--output-format=json"),
    "clippy": ("cargo", "clippy", "--no-deps", "--message-format=json", "--quiet"),
    "eslint": ("npx", "--no-install", "eslint", "--format=json", "."),
    "golangci-lint": ("golangci-lint", "run", "--out-format=json"),
    "spotbugs": ("mvn", "-q", "spotbugs:spotbugs"),
}


def _capture_run(returncode=0, stdout="", stderr=""):
    """Patch subprocess.run and return the recorded (argv, kwargs) calls."""

    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)

    return calls, fake_run

def test_run_scanner_uses_native_argv_and_no_shell():
    root = Path(__file__).parent
    calls, fake_run = _capture_run(returncode=1, stdout="[]")
    with mock.patch.object(scan_code.subprocess, "run", fake_run), \
         mock.patch.object(scan_code.shutil, "which", lambda name: f"/usr/bin/{name}"):
        findings = scan_code.run_scanner(root, SCANNER_ARGS["ruff"], "ruff")
    assert len(calls) == 1, calls
    argv, kwargs = calls[0]
    assert argv == list(SCANNER_ARGS["ruff"]), argv
    assert kwargs["shell"] is False, kwargs
    assert kwargs["cwd"] == str(root), kwargs
    assert kwargs["timeout"] == 300, kwargs
    assert findings == [], findings


def test_every_declared_scanner_passes_its_argv_unchanged():
    root = Path(__file__).parent
    for parser, argv in SCANNER_ARGS.items():
        calls, fake_run = _capture_run(returncode=1, stdout="[]")
        with mock.patch.object(scan_code.subprocess, "run", fake_run), \
             mock.patch.object(scan_code.shutil, "which", lambda name: f"/usr/bin/{name}"):
            scan_code.run_scanner(root, argv, parser)
        assert calls[0][0] == list(argv), (parser, calls[0][0])
        assert calls[0][1]["shell"] is False, parser


def test_a_missing_binary_degrades_to_a_warning():
    with mock.patch.object(scan_code.shutil, "which", lambda name: None):
        findings = scan_code.run_scanner(Path("."), SCANNER_ARGS["ruff"], "ruff")
    assert findings and "not found" in findings[0]["warning"], findings


def test_an_unexpected_returncode_reports_the_stderr_tail():
    root = Path(__file__).parent
    calls, fake_run = _capture_run(returncode=2, stderr="boom")
    with mock.patch.object(scan_code.subprocess, "run", fake_run), \
         mock.patch.object(scan_code.shutil, "which", lambda name: f"/usr/bin/{name}"):
        findings = scan_code.run_scanner(root, SCANNER_ARGS["ruff"], "ruff")
    assert findings[0]["warning"] == "scanner exited with code 2", findings
    assert "boom" in findings[0]["stderr_tail"]


def test_a_timeout_degrades_to_a_warning():
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ruff", timeout=300)

    with mock.patch.object(scan_code.subprocess, "run", fake_run), \
         mock.patch.object(scan_code.shutil, "which", lambda name: f"/usr/bin/{name}"):
        findings = scan_code.run_scanner(Path("."), SCANNER_ARGS["ruff"], "ruff")
    assert findings == [{"warning": "scanner timed out after 300s"}], findings


def test_windows_cmd_shims_go_through_cmd_without_a_shell_string():
    argv = ("npx", "--no-install", "eslint", "--format=json", ".")
    resolved = "C:\\Program Files\\nodejs\\npx.cmd"
    built = scan_code.executable_argv(argv, platform_name="nt",
                                      which=lambda name: resolved)
    assert built == ["cmd", "/c", resolved, "--no-install", "eslint",
                     "--format=json", "."], built


def test_posix_and_real_executables_are_returned_unchanged():
    assert scan_code.executable_argv(("ruff", "check"), platform_name="posix") == \
        ["ruff", "check"]
    built = scan_code.executable_argv(("mvn", "-q"), platform_name="nt",
                                      which=lambda name: "C:\\tools\\mvn.exe")
    assert built == ["mvn", "-q"], built

CLIPPY_REALISTIC = json.dumps({
    "reason": "compiler-message",
    "message": {
        "code": {"code": "clippy::needless_return"},
        "message": "unneeded `return` statement",
        "spans": [
            {"file_name": "src/lib.rs", "line_start": 12, "line_end": 12,
             "is_primary": True},
        ],
    },
})


def test_normalize_clippy_realistic_json():
    findings = scan_code.normalize_clippy(CLIPPY_REALISTIC, Path("."))
    assert len(findings) == 1, findings
    finding = findings[0]
    assert finding["description"].startswith("clippy::needless_return"), finding
    assert finding["location"]["file"] == "src/lib.rs", finding["location"]
    assert finding["location"]["lines"] == "12", finding["location"]


def test_normalize_clippy_multiple_spans_picks_the_primary():
    line = json.dumps({
        "reason": "compiler-message",
        "message": {
            "code": {"code": "clippy::redundant_clone"},
            "message": "redundant clone",
            "spans": [
                {"file_name": "secondary.rs", "line_start": 1, "is_primary": False},
                {"file_name": "primary.rs", "line_start": 42, "is_primary": True},
            ],
        },
    })
    findings = scan_code.normalize_clippy(line, Path("."))
    assert len(findings) == 1, findings
    assert findings[0]["location"]["file"] == "primary.rs", findings[0]["location"]
    assert findings[0]["location"]["lines"] == "42", findings[0]["location"]


def test_normalize_clippy_missing_span_is_skipped():
    line = json.dumps({"reason": "compiler-message",
                       "message": {"code": {"code": "clippy::x"},
                                   "message": "y", "spans": []}})
    assert scan_code.normalize_clippy(line, Path(".")) == []


def test_normalize_clippy_missing_code_is_skipped():
    line = json.dumps({"reason": "compiler-message",
                       "message": {"code": None, "message": "y",
                                   "spans": [{"file_name": "f", "line_start": 1,
                                              "is_primary": True}]}})
    assert scan_code.normalize_clippy(line, Path(".")) == []


def test_normalize_clippy_malformed_lines_are_skipped_not_raised():
    payload = "not json\n{\"reason\": \"build-finished\"}\n" + CLIPPY_REALISTIC
    findings = scan_code.normalize_clippy(payload, Path("."))
    assert len(findings) == 1, findings


def test_real_ruff_process_smoke():
    if shutil.which("ruff") is None:
        print("[SKIP] ruff not installed; the mocked contracts above already ran")
        return
    import tempfile

    with tempfile.TemporaryDirectory(prefix="scan-code-smoke-") as staging:
        root = Path(staging)
        (root / "pyproject.toml").write_text("[project]\nname = 'smoke'\n",
                                             encoding="utf-8")
        (root / "mod.py").write_text("import os\n", encoding="utf-8")
        findings = scan_code.run_scanner(root, SCANNER_ARGS["ruff"], "ruff")
        assert not any("warning" in finding for finding in findings), findings
        codes = [finding["description"].split(":", 1)[0] for finding in findings]
        assert any(code == "F401" for code in codes), codes


if __name__ == "__main__":
    failures = []
    for _name, _function in sorted(globals().items()):
        if _name.startswith("test_") and callable(_function):
            try:
                _function()
                print(f"OK: {_name}")
            except AssertionError as _error:
                failures.append(_name)
                print(f"FAILED: {_name}: {_error}")
    if failures:
        raise SystemExit(f"{len(failures)} test(s) failed: {', '.join(failures)}")
    print("all scan-code execution tests passed")