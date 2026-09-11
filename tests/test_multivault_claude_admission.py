import tempfile
import unittest
from pathlib import Path

from ainative.multivault.harness_claude import (
    CLAUDE_INSTRUCTIONS_REASON_CODE,
    PROJECT_INSTRUCTION_SCAN_INCOMPLETE_CODE,
    SensitivePhaseGate,
    instruction_admission_record,
)


class ClaudeInstructionAdmissionTests(unittest.TestCase):
    def test_denies_cwd_claude_md(self):
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as base:
            ws = P(base) / "ws"
            ws.mkdir()
            (ws / "CLAUDE.md").write_text("rule", encoding="utf-8")
            record = instruction_admission_record(ws)
            self.assertEqual("DENY_NOT_DISABLEABLE", record.decision)
            self.assertEqual(CLAUDE_INSTRUCTIONS_REASON_CODE, record.reason_code)

    def test_denies_cwd_dotclaude_claude_md(self):
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as base:
            ws = P(base) / "ws"
            (ws / ".claude").mkdir(parents=True)
            (ws / ".claude" / "CLAUDE.md").write_text("rule", encoding="utf-8")
            self.assertEqual("DENY_NOT_DISABLEABLE", instruction_admission_record(ws).decision)

    def test_denies_claude_local_md(self):
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as base:
            ws = P(base) / "ws"
            ws.mkdir()
            (ws / "CLAUDE.local.md").write_text("rule", encoding="utf-8")
            self.assertEqual("DENY_NOT_DISABLEABLE", instruction_admission_record(ws).decision)

    def test_denies_applicable_parent_claude_md(self):
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as base:
            ws = P(base) / "child"
            ws.mkdir()
            (P(base) / "CLAUDE.md").write_text("rule", encoding="utf-8")
            self.assertEqual("DENY_NOT_DISABLEABLE", instruction_admission_record(ws).decision)

    def test_allows_when_all_applicable_surfaces_absent(self):
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as base:
            ws = P(base) / "ws"
            ws.mkdir()
            record = instruction_admission_record(ws)
            self.assertEqual("ALLOW", record.decision)
            self.assertEqual((), record.applicable_surfaces)
            self.assertEqual("OK", record.reason_code)

    def test_does_not_treat_user_global_claude_md_as_workspace_surface(self):
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as home:
            root = P(home)
            (root / ".claude").mkdir()
            (root / ".claude" / "CLAUDE.md").write_text("user memory", encoding="utf-8")
            ws = root / "projects" / "ws"
            ws.mkdir(parents=True)
            self.assertEqual("ALLOW", instruction_admission_record(ws).decision)

    def test_scan_incomplete_denies_sensitive(self):
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as base:
            record = instruction_admission_record(P(base) / "missing")
            self.assertEqual("DENY_OBSERVATION_INCOMPLETE", record.decision)
            self.assertEqual(PROJECT_INSTRUCTION_SCAN_INCOMPLETE_CODE, record.reason_code)

    def test_policy_checked_then_rechecked_before_phase_b(self):
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as base:
            ws = P(base) / "ws"
            ws.mkdir()
            gate = SensitivePhaseGate(ws)
            self.assertEqual("ALLOW", gate.phase_a().decision)
            (ws / "CLAUDE.md").write_text("rule appears after phase A", encoding="utf-8")
            self.assertEqual("DENY_NOT_DISABLEABLE", gate.phase_b().decision)

    def test_phase_b_without_phase_a_is_incomplete(self):
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as base:
            ws = P(base) / "ws"
            ws.mkdir()
            self.assertEqual("DENY_OBSERVATION_INCOMPLETE", SensitivePhaseGate(ws).phase_b().decision)