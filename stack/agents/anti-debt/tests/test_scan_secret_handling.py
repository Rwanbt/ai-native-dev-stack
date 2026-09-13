"""test_scan_secret_handling.py — secrets are fingerprinted, never previewed.

The security scanner used to persist `raw[:8] + "..."` in finding ids and
evidence, so any report - or CI log containing one - leaked the leading bytes
of every detected secret (AUD-203). These tests pin the replacement contract:
a non-reversible SHA-256 fingerprint, stable for the same input and distinct
for a different one, with no fragment of the secret anywhere in the output.

They also pin the failure boundary introduced with #127's fix: an absent
external tool degrades to a warning; a defect in this scanner's own parser
raises instead of being relabelled as a scanner warning.
"""
import importlib.util
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).parent.parent / "skills" / "debt-scan" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("scan_security", TOOLS / "scan_security.py")
scan_security = importlib.util.module_from_spec(_spec)
sys.modules["scan_security"] = scan_security
_spec.loader.exec_module(scan_security)

# The canonical AWS documentation example key: fixture-shaped, never real.
FIXTURE_SECRET = "AKIAIOSFODNN7EXAMPLE"
OTHER_SECRET = "AKIAIOSFODNN7EXAMPLZ"


def trufflehog_payload(secret=FIXTURE_SECRET, verified=True):
    return json.dumps({
        "DetectorName": "AWS",
        "Verified": verified,
        "Raw": secret,
        "SourceMetadata": {"Data": {"Filesystem": {"file": "src/config.py"}}},
    })


def assert_no_secret_fragment(serialized: str) -> None:
    assert FIXTURE_SECRET not in serialized, "the raw secret reached the report"
    assert FIXTURE_SECRET[:4] not in serialized, "a 4-char preview reached the report"
    assert FIXTURE_SECRET[:8] not in serialized, "an 8-char preview reached the report"
    assert "..." not in serialized, "the old preview shape is still emitted"


def test_trufflehog_reports_carry_no_secret_fragment():
    findings = scan_security.normalize_trufflehog(trufflehog_payload())
    assert len(findings) == 1, findings
    assert_no_secret_fragment(json.dumps(findings))
    assert "fingerprint=" in findings[0]["evidence"][1]["value"], findings[0]


def test_trufflehog_fingerprint_is_stable_and_input_specific():
    first = scan_security.normalize_trufflehog(trufflehog_payload())[0]
    again = scan_security.normalize_trufflehog(trufflehog_payload())[0]
    other = scan_security.normalize_trufflehog(
        trufflehog_payload(secret=OTHER_SECRET))[0]
    assert first["id"] == again["id"], "the same secret produced two identities"
    assert first["id"] != other["id"], "two secrets produced one identity"
    fingerprint = first["evidence"][1]["value"].split("fingerprint=")[1]
    assert len(fingerprint) == 12, fingerprint
    assert all(character in "0123456789abcdef" for character in fingerprint)


def test_verified_and_unverified_keep_their_severity():
    verified = scan_security.normalize_trufflehog(trufflehog_payload(verified=True))[0]
    unverified = scan_security.normalize_trufflehog(
        trufflehog_payload(verified=False))[0]
    assert verified["severity"] == "critical"
    assert unverified["severity"] == "high"


def test_gitleaks_reports_carry_no_secret_fragment():
    payload = json.dumps([{
        "File": "src/app.py", "StartLine": 3, "RuleID": "aws-access-token",
        "Secret": FIXTURE_SECRET,
    }])
    findings = scan_security.normalize_gitleaks(payload)
    assert len(findings) == 1, findings
    assert_no_secret_fragment(json.dumps(findings))
    assert "fingerprint=" in findings[0]["evidence"][1]["value"], findings[0]
    assert FIXTURE_SECRET[:4] not in findings[0]["id"], findings[0]["id"]


def test_fingerprint_helper_is_stable_and_non_reversible():
    from finding_common import secret_fingerprint

    assert secret_fingerprint(FIXTURE_SECRET) == secret_fingerprint(FIXTURE_SECRET)
    assert secret_fingerprint(FIXTURE_SECRET) != secret_fingerprint(OTHER_SECRET)
    fingerprint = secret_fingerprint(FIXTURE_SECRET)
    assert len(fingerprint) == 12
    assert FIXTURE_SECRET[:8] not in fingerprint


def test_a_parser_defect_raises_instead_of_degrading_to_a_warning():
    # A JSON array where the parser expects objects: this is the #127 class,
    # and it must surface as a failed scan, not as `scanner failed: ...`.
    try:
        scan_security.normalize_trufflehog(json.dumps(["not-an-object"]))
    except AttributeError:
        return
    raise AssertionError("a parser defect was swallowed into a warning")


def test_a_missing_tool_is_reported_not_raised():
    assert scan_security.is_installed(["ainative-no-such-tool-xyz", "--version"]) is False


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
    print("all scan secret-handling tests passed")