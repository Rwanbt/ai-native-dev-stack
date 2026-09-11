import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative.multivault.audit import AuditLog, AuditRecord
from ainative.multivault.status import (
    CHECK_FAIL,
    CHECK_PASS,
    CHECK_UNKNOWN,
    ContextReport,
    doctor_check,
    doctor_report,
    qualification_label,
)


def record(**overrides) -> AuditRecord:
    fields = {
        "timestamp": "2026-09-11T12:00:00Z",
        "security_domain_id": "company-a",
        "operation": "push.authorize",
        "decision": "DENY",
        "reason_code": "AINATIVE_PUSH_CAPABILITY_EXPIRED",
        "harness": "opencode",
        "provider_class": "local_runtime",
        "model_identifier": "local-model",
        "remote_stable_id": "R_kgDOAAAAAA",
        "transport_digest": "transport-digest",
        "revocation_cause": "expiry",
        "qualification_level": "GUARDED",
    }
    fields.update(overrides)
    return AuditRecord(**fields)


class AuditTests(unittest.TestCase):
    def test_records_append_and_query_with_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            log = AuditLog(Path(directory) / "audit.jsonl")
            log.append(record())
            log.append(record(security_domain_id="company-b", decision="ALLOW", reason_code="OK"))
            self.assertEqual(2, len(log.query()))
            self.assertEqual(1, len(log.query(security_domain_id="company-b")))
            self.assertEqual(1, len(log.query(decision="DENY")))
            self.assertEqual(1, len(log.query(reason_code="OK")))

    def test_missing_core_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            record(operation="").validate()

    def test_unsupported_or_bare_qualification_is_rejected(self):
        with self.assertRaises(ValueError):
            record(qualification_level="ENFORCED").validate()
        with self.assertRaises(ValueError):
            record(qualification_level="PRODUCTION").validate()

    def test_multiline_or_oversized_values_are_rejected(self):
        with self.assertRaises(ValueError):
            record(reason_code="secret\nvalue").validate()
        with self.assertRaises(ValueError):
            record(reason_code="x" * 201).validate()

    def test_cli_prints_matching_records_as_json_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "audit.jsonl"
            AuditLog(log_path).append(record())
            result = subprocess.run(
                [sys.executable, "-m", "ainative.multivault", "audit-query", str(log_path), "--decision", "DENY"],
                capture_output=True,
                text=True,
                cwd=str(Path.cwd()),
            )
            self.assertEqual(0, result.returncode)
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(1, len(lines))
            self.assertEqual("company-a", json.loads(lines[0])["security_domain_id"])


class StatusTests(unittest.TestCase):
    def report(self, **overrides) -> ContextReport:
        fields = {
            "security_domain_id": "company-a",
            "classification": "CONFIDENTIAL",
            "vault_identity": "vault-a",
            "checkout_identity": "checkout-a",
            "harness": "opencode",
            "provider_class": "local_runtime",
            "model": "local-model",
            "routing": "direct",
            "qualification": "GUARDED",
            "observation_windows": ("event",),
            "unsupported_capabilities": ("model_egress",),
            "supported": False,
        }
        fields.update(overrides)
        return ContextReport(**fields)

    def test_bare_enforced_is_never_a_valid_label(self):
        for level in ("ENFORCED", "PRODUCTION", ""):
            with self.assertRaises(ValueError):
                qualification_label(level)

    def test_displayable_labels_are_returned_verbatim(self):
        for level in ("UNKNOWN", "GUARDED", "ENFORCED-DIAGNOSTIC", "ENFORCED-AUTHENTICATED"):
            self.assertEqual(level, qualification_label(level))

    def test_context_report_render_contains_the_fail_closed_state(self):
        rendered = self.report().render()
        self.assertIn("qualification: GUARDED", rendered)
        self.assertIn("supported: no", rendered)
        self.assertIn("unsupported_capabilities: model_egress", rendered)

    def test_doctor_check_fails_closed(self):
        self.assertEqual(CHECK_UNKNOWN, doctor_check(None))
        self.assertEqual(CHECK_FAIL, doctor_check(False))
        self.assertEqual(CHECK_FAIL, doctor_check(True, fresh=False))
        self.assertEqual(CHECK_PASS, doctor_check(True))

    def test_doctor_report_is_sorted_and_never_upgrades_unknown(self):
        report = doctor_report({"canary": None, "hooks": False, "vault": True})
        self.assertEqual((("canary", CHECK_UNKNOWN), ("hooks", CHECK_FAIL), ("vault", CHECK_PASS)), report)