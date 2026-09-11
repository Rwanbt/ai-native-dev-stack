# MV-00.4 — Harness autoload report

## Executed evidence

```text
python scripts/mv00/harness_autoload.py --checkout .
```

The probe inventories filenames only and does not parse or execute configuration.

## Result

Recognized project-local surfaces are present: `AGENTS.md` and two OpenCode JSON files.

```text
disable_control = UNKNOWN
observation = none
CONFIDENTIAL/CRITICAL harness capability = unavailable
```

The next required evidence is a versioned neutral-launch probe for each target harness.
