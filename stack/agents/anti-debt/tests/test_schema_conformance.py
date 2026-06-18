"""test_schema_conformance.py — Real scanner output MUST conform to the schema.

The previous review found 78/78 real findings violating debt-finding.schema.json
(evidence.type / source / category enums) while the hand-written examples passed.
Schema validation of *curated examples* is "trust me" evidence. This guard runs
the actual deterministic scanners and validates their output, so the
schema↔scanner contract can never silently drift again.

Uses `jsonschema` when available (CI installs it); otherwise falls back to a
manual enum/required check that covers the same drift modes.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "debt-finding.schema.json").read_text(encoding="utf-8"))
TRIAGE_SCHEMA = json.loads((ROOT / "schemas" / "debt-triage.schema.json").read_text(encoding="utf-8"))
FIXTURE = ROOT / "tests" / "corpus" / "fixtures" / "fixture1-py-messy"
sys.path.insert(0, str(ROOT / "tools"))

# Scanners that run with no external toolchain (pure Python) — always produce output.
SCANNERS = [
    [sys.executable, str(ROOT / "tools" / "static_analysis.py"), str(ROOT)],
    [sys.executable, str(ROOT / "skills" / "debt-scan" / "tools" / "scan_code.py"), str(FIXTURE)],
    [sys.executable, str(ROOT / "skills" / "debt-architecture" / "tools" / "scan_architecture.py"), str(ROOT)],
]


def _collect_findings() -> list[dict]:
    findings = []
    for cmd in SCANNERS:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=300)
        if not proc.stdout.strip():
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        for f in data.get("findings", []):
            if isinstance(f, dict) and "category" in f and "warning" not in f:
                findings.append(f)
    return findings


def _manual_validate(f: dict) -> list[str]:
    """Return a list of schema violations for one finding (empty = valid)."""
    errs = []
    props = SCHEMA["properties"]
    for req in SCHEMA["required"]:
        if req not in f:
            errs.append(f"missing required '{req}'")
    if f.get("category") not in props["category"]["enum"]:
        errs.append(f"category '{f.get('category')}' not in enum")
    if f.get("severity") not in props["severity"]["enum"]:
        errs.append(f"severity '{f.get('severity')}' not in enum")
    if f.get("source") not in props["source"]["enum"]:
        errs.append(f"source '{f.get('source')}' not in enum")
    ev_enum = props["evidence"]["items"]["properties"]["type"]["enum"]
    for ev in f.get("evidence", []):
        if ev.get("type") not in ev_enum:
            errs.append(f"evidence.type '{ev.get('type')}' not in enum")
    if "estimated_effort" in f and f["estimated_effort"] not in props["estimated_effort"]["enum"]:
        errs.append(f"estimated_effort '{f['estimated_effort']}' not in enum")
    c = f.get("confidence")
    if not isinstance(c, (int, float)) or not (0 <= c <= 1):
        errs.append(f"confidence '{c}' out of [0,1]")
    return errs


def test_scanner_output_conforms_to_schema():
    findings = _collect_findings()
    assert findings, "scanners produced no findings — cannot validate conformance"

    try:
        import jsonschema  # type: ignore
        validator = jsonschema.Draft7Validator(SCHEMA)
        failures = []
        for f in findings:
            errs = sorted(e.message for e in validator.iter_errors(f))
            if errs:
                failures.append((f.get("id"), errs))
    except ImportError:
        failures = [(f.get("id"), errs) for f in findings if (errs := _manual_validate(f))]

    assert not failures, (
        f"{len(failures)}/{len(findings)} findings violate debt-finding.schema.json:\n"
        + "\n".join(f"  {fid}: {errs}" for fid, errs in failures[:10])
    )
    print(f"[PASS] {len(findings)} real scanner findings conform to schema")


def test_finding_ids_are_deterministic():
    """Same code scanned twice yields identical finding ids (stable identity)."""
    a = {f["id"] for f in _collect_findings()}
    b = {f["id"] for f in _collect_findings()}
    assert a == b, "finding ids changed between identical scans — identity not stable"
    print(f"[PASS] {len(a)} finding ids stable across runs")


def _validate(obj: dict, schema: dict) -> list[str]:
    try:
        import jsonschema  # type: ignore
        return sorted(e.message for e in jsonschema.Draft7Validator(schema).iter_errors(obj))
    except ImportError:
        # Minimal fallback: required keys + additionalProperties at root.
        errs = [f"missing '{r}'" for r in schema.get("required", []) if r not in obj]
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}))
            errs += [f"unexpected key '{k}'" for k in obj if k not in allowed]
        return errs


def test_triage_conforms_to_schema():
    """build_triage output (incl. mvp_runtime enrichment) conforms to debt-triage."""
    import critic_v2
    findings = [
        {"id": "f-a", "category": "code", "subcategory": "complexity", "severity": "high",
         "confidence": 0.9, "location": {"file": "x.py", "lines": "1"}},
        {"id": "f-b", "category": "code", "subcategory": "duplication", "severity": "low",
         "confidence": 0.5, "location": {"file": "y.py", "lines": "2"}},
    ]
    triage = critic_v2.build_triage(findings, project="proj")
    errs = _validate(triage, TRIAGE_SCHEMA)
    assert not errs, f"raw triage violates schema: {errs}"

    # Enrich exactly like mvp_runtime does, then re-validate.
    triage["mode"] = "complete"
    triage["scope"] = {"categories_covered": ["code"], "plan_completeness": "complete"}
    triage["critic_validation"]["plan_completeness"] = "complete"
    errs = _validate(triage, TRIAGE_SCHEMA)
    assert not errs, f"enriched triage violates schema: {errs}"
    print("[PASS] triage (raw + enriched) conforms to debt-triage.schema.json")


def test_example_debtplan_conforms():
    """The reference DebtPlan example must conform to debt-plan.schema.json.

    Locks the judgment-half contract: if the example (the canonical shape the
    LLM debt-plan skill targets) drifts from the schema, this fails.
    """
    plan_schema = json.loads((ROOT / "schemas" / "debt-plan.schema.json").read_text(encoding="utf-8"))
    example = json.loads((ROOT / "examples" / "sample-debt-plan.json").read_text(encoding="utf-8"))
    errs = _validate(example, plan_schema)
    assert not errs, f"sample-debt-plan.json violates debt-plan.schema.json: {errs}"
    print("[PASS] reference DebtPlan conforms to debt-plan.schema.json")


if __name__ == "__main__":
    failed = 0
    for t in (test_scanner_output_conforms_to_schema, test_finding_ids_are_deterministic,
              test_triage_conforms_to_schema, test_example_debtplan_conforms):
        try:
            t()
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    sys.exit(1 if failed else 0)
