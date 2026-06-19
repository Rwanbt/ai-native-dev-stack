#!/usr/bin/env python3
"""validate_plan.py — Validate an LLM-authored DebtPlan against its schema.

The `debt-plan` skill produces plan.json by JUDGMENT (the LLM groups findings
into actions and justifies accepted debt). Unlike the deterministic triage,
nothing guarantees its shape — so it MUST be validated before publication.
This is the schema gate for the judgment half of the pipeline (Option B).

Usage:
    python3 validate_plan.py plan.json
Exit 0 = valid, 1 = invalid (violations printed), 2 = usage error.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "debt-plan.schema.json"


def validate(plan: dict, schema: dict) -> list[str]:
    """Return a list of violations (empty = valid). Uses jsonschema if present."""
    try:
        import jsonschema  # type: ignore
        return sorted(e.message for e in jsonschema.Draft7Validator(schema).iter_errors(plan))
    except ImportError:
        # Fallback: required keys + root additionalProperties + mode enum.
        errs = [f"missing required '{r}'" for r in schema.get("required", []) if r not in plan]
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}))
            errs += [f"unexpected root key '{k}'" for k in plan if k not in allowed]
        mode_enum = schema["properties"]["mode"]["enum"]
        if plan.get("mode") not in mode_enum:
            errs.append(f"mode '{plan.get('mode')}' not in {mode_enum}")
        return errs


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: validate_plan.py <plan.json>"}))
        return 2
    plan_path = Path(sys.argv[1])
    if not plan_path.exists():
        print(json.dumps({"error": f"not found: {plan_path}"}))
        return 2
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    errs = validate(plan, schema)
    if errs:
        print(json.dumps({"valid": False, "violations": errs}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({"valid": True, "plan": str(plan_path)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
