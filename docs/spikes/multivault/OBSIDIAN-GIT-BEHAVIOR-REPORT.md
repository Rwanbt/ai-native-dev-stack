# MV-00.3 — Obsidian Git behavior report

## Executed evidence

```text
python scripts/mv00/obsidian_git.py --vault-root D:\Documents\Obsidian\IA_Dev_Brain
```

The probe reads only plugin metadata and setting names. It neither reads setting values
nor runs a Git transfer.

## Observed tuple

| Property | Observation |
|---|---|
| Plugin | Obsidian Git |
| Version | 2.39.0 |
| Enabled | yes |
| Potential writer controls | automatic backup, pull, push, scheduled intervals |
| Active scheduling/process observer | none |

## Result

```text
concurrent_writer = UNKNOWN
CONFIDENTIAL/CRITICAL sync capability = unavailable
```

The frozen V1 rule denies sensitive sync whenever an active concurrent writer cannot be
excluded. Inspecting configuration names cannot establish whether schedules are disabled
or whether a running plugin is currently transferring. MV-19 must therefore use its own
governed transfer path rather than treat this plugin as a trusted writer.
