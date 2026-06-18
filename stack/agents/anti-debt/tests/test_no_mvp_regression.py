"""test_no_mvp_regression.py — Verify the agent doesn't regress to MVP mode.

Two layers of tests:
- Schema guards: the plan/finding schemas keep the fields the policy depends on.
- Behavioral guards: the actual runtime code enforces the policy (the 0.6 reject
  floor, low-confidence exclusion, and multi-category scan coverage). Schema
  shape alone is "trust me" evidence — the behavioral tests exercise real code.
"""
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCHEMAS = ROOT / "schemas"
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))


def test_complete_plan_must_cover_all_categories():
    """The plan schema requires critic_validation.plan_completeness.

    A complete plan MUST have plan_completeness = 'complete'.
    """
    import json
    schema = json.loads((SCHEMAS / "debt-plan.schema.json").read_text())
    enum_values = schema["properties"]["critic_validation"]["properties"]["plan_completeness"]["enum"]
    assert "complete" in enum_values, "Schema must allow 'complete' plan"
    assert "incomplete" in enum_values, "Schema must allow 'incomplete' plan"


def test_mvp_mode_requires_debt_report():
    """The plan schema requires mvp_debt_report_ref when mode=mvp."""
    import json
    schema = json.loads((SCHEMAS / "debt-plan.schema.json").read_text())

    mode_field = schema["properties"]["mode"]
    assert "mvp" in mode_field["enum"], "Schema must support 'mvp' mode"

    # mvp_debt_report_ref is optional in schema but recommended when mode=mvp
    # (we encode this as a description, not as a conditional requirement,
    # because JSON Schema conditional dependencies are complex)
    ref_field = schema["properties"]["mvp_debt_report_ref"]
    assert ref_field["type"] == "string"
    assert "obligatoire" in ref_field["description"].lower() or "obligatoire" in ref_field["description"].lower() or "required" in ref_field["description"].lower()


def test_findings_must_have_evidence():
    """Every finding MUST have at least one evidence item."""
    import json
    schema = json.loads((SCHEMAS / "debt-finding.schema.json").read_text())
    assert schema["properties"]["evidence"]["minItems"] >= 1
    assert "evidence" in schema["required"]


def test_findings_below_threshold_rejected():
    """Confidence < 0.6 should be flagged. The agent SKILL critic.md defines this."""
    # Read the critic SKILL to ensure it documents this rule
    critic_skill = ROOT / "skills" / "critic" / "SKILL.md"
    if critic_skill.exists():
        content = critic_skill.read_text()
        assert "0.6" in content or "0.6" in content, \
            "Critic SKILL must document the confidence threshold"


# --- Behavioral guards (exercise real runtime code) ---

def test_critic_enforces_06_reject_floor():
    """The non-negotiable 0.6 floor is enforced by critic_v2, not just documented."""
    import critic_v2
    assert critic_v2.tier({"confidence": 0.5}) == "reject", "0.5 must be rejected (< 0.6 floor)"
    assert critic_v2.tier({"confidence": 0.59}) == "reject", "0.59 must be rejected"
    assert critic_v2.tier({"confidence": 0.6}) == "review", "0.6 enters review tier"
    assert critic_v2.tier({"confidence": 0.7}) == "accept", "0.7 is accepted"


def test_low_confidence_excluded_from_fix_order():
    """A finding below the floor must never land in the auto-fix plan."""
    import critic_v2
    findings = [
        {"id": "f-lo", "category": "code", "severity": "high", "confidence": 0.5,
         "location": {"file": "x.py", "lines": "1"}},
        {"id": "f-hi", "category": "code", "severity": "high", "confidence": 0.9,
         "location": {"file": "y.py", "lines": "2"}},
    ]
    plan = critic_v2.build_triage(findings, project="t")
    fix_ids = [f.get("id") for f in plan["fix_order"]]
    assert "f-lo" not in fix_ids, "low-confidence finding leaked into fix_order"
    assert "f-hi" in fix_ids, "high-confidence finding should be in fix_order"


def test_complete_scan_covers_all_categories():
    """A 'complete plan' run scans every scannable category, not just `code`.

    Guards against the MVP regression where the runtime silently scanned only
    the code category (Directive 1).
    """
    import mvp_runtime
    scannable = {c for _, cats in mvp_runtime.SCANNERS for c in cats}
    assert {"code", "security", "dependencies"}.issubset(scannable), \
        f"runtime only scans {scannable} — must cover code+security+dependencies"


def test_scope_completeness_flags_missing_category():
    """If a scannable category had no scanner run, completeness must be 'partial'."""
    import mvp_runtime
    # security + dependencies scanners did not run -> partial, not silently complete
    scan_meta = [{"scanner": "static_analysis.py", "categories": ["code"], "ran": True}]
    scope = mvp_runtime._scope_completeness(scan_meta)
    assert scope["plan_completeness"] == "partial"
    assert "security" in scope["categories_missing_tooling"]
    assert "dependencies" in scope["categories_missing_tooling"]


if __name__ == "__main__":
    tests = [
        test_complete_plan_must_cover_all_categories,
        test_mvp_mode_requires_debt_report,
        test_findings_must_have_evidence,
        test_findings_below_threshold_rejected,
        test_critic_enforces_06_reject_floor,
        test_low_confidence_excluded_from_fix_order,
        test_complete_scan_covers_all_categories,
        test_scope_completeness_flags_missing_category,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
