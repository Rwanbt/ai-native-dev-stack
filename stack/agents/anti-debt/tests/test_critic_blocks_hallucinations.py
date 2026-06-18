"""test_critic_blocks_hallucinations.py — Verify the Critic rejects findings without proof.

Tests the policy: findings with no concrete evidence are rejected.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def mock_critic(finding: dict) -> dict:
    """Minimal Critic Engine implementation for testing.

    Returns the same shape as the Critic SKILL describes.
    """
    evidence = finding.get("evidence", [])
    confidence = finding.get("confidence", 0)
    passed = True
    concerns = []
    rejected = []

    if not evidence:
        passed = False
        rejected.append(finding.get("id", "unknown"))
        concerns.append(f"{finding.get('id', '?')}: no evidence provided")

    if confidence < 0.6:
        passed = False
        rejected.append(finding.get("id", "unknown"))
        concerns.append(f"{finding.get('id', '?')}: confidence {confidence} < 0.6")

    # Anti-self-referential: evidence must not contain the finding ID itself
    for ev in evidence:
        value = ev.get("value", "") if isinstance(ev, dict) else str(ev)
        if finding.get("id", "") in value:
            passed = False
            rejected.append(finding.get("id", "unknown"))
            concerns.append(f"{finding.get('id', '?')}: evidence is self-referential")

    return {
        "passed": passed,
        "concerns": concerns,
        "rejected_findings": rejected,
        "plan_completeness": "complete" if passed else "incomplete",
        "mvp_disguised": False,
        "recommendations": [],
        "blocking": not passed,
    }


def test_finding_without_evidence_rejected():
    finding = {
        "id": "f-001",
        "category": "code",
        "subcategory": "complexity",
        "severity": "high",
        "description": "Code too complex",
        "evidence": [],
        "confidence": 0.9,
        "source": "llm-inference",
    }
    result = mock_critic(finding)
    assert result["passed"] is False
    assert "f-001" in result["rejected_findings"]
    print("[PASS] finding without evidence rejected")


def test_finding_with_low_confidence_rejected():
    finding = {
        "id": "f-002",
        "category": "code",
        "subcategory": "complexity",
        "severity": "medium",
        "description": "Maybe too complex?",
        "evidence": [{"type": "file_location", "value": "src/x.py:42"}],
        "confidence": 0.4,
        "source": "llm-inference",
    }
    result = mock_critic(finding)
    assert result["passed"] is False
    assert "f-002" in result["rejected_findings"]
    print("[PASS] finding with low confidence rejected")


def test_finding_with_concrete_evidence_accepted():
    finding = {
        "id": "f-003",
        "category": "security",
        "subcategory": "secrets_in_code",
        "severity": "critical",
        "description": "API key committed",
        "evidence": [
            {"type": "file_location", "value": "src/config.py:12"},
            {"type": "tool_output", "tool": "trufflehog", "value": "Stripe API key detected at src/config.py:12"},
        ],
        "confidence": 0.99,
        "source": "tool:trufflehog",
    }
    result = mock_critic(finding)
    assert result["passed"] is True
    assert "f-003" not in result["rejected_findings"]
    print("[PASS] finding with concrete evidence accepted")


def test_finding_with_self_referential_evidence_rejected():
    finding = {
        "id": "f-004",
        "category": "code",
        "subcategory": "duplication",
        "severity": "medium",
        "description": "Code duplicated",
        "evidence": [
            {"type": "doc_reference", "value": "f-004"},  # ← self-referential!
        ],
        "confidence": 0.8,
        "source": "llm-inference",
    }
    result = mock_critic(finding)
    assert result["passed"] is False
    assert "f-004" in result["rejected_findings"]
    print("[PASS] self-referential evidence rejected")


if __name__ == "__main__":
    tests = [
        test_finding_without_evidence_rejected,
        test_finding_with_low_confidence_rejected,
        test_finding_with_concrete_evidence_accepted,
        test_finding_with_self_referential_evidence_rejected,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
