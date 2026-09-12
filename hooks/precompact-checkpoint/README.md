# precompact-checkpoint (PreCompact)

Freezes the bounded operational state before compaction. The state is fixed
and minimal on purpose: a hook must not invent observations.

Registration (example, .claude/settings.json):

```json
{"hooks": {"PreCompact": [{"hooks": [{"type": "command",
  "command": "python /absolute/path/hooks/precompact-checkpoint/run.py"}]}]}}
```

Boundary: checkpoint only. No capture, no consolidation, no promotion.
