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

## Neutral-launch follow-up — OpenCode 1.18.23

Executed evidence:

```text
python scripts/mv00/harness_neutral_launch.py --output docs/spikes/multivault/HARNESS-NEUTRAL-LAUNCH-OPENCODE.json
```

Observed in a neutral project:

- project `opencode.json` agent autoload = VERIFIED
- project `.opencode/skills/<name>/SKILL.md` autoload = VERIFIED (listed with its project location)
- `--pure` does not change it (plugins-only switch)
- `disable_control = UNKNOWN`, `observation = per_operation`

CONFIDENTIAL/CRITICAL harness capability remains unavailable: no proven
switch suppresses project autoload, so sensitive admission still denies.
