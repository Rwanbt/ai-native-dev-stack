# session-start-context (SessionStart)

Restores the latest working checkpoint and reports the working footprint.
Read-only with respect to canonical content: it never invents state - a moved
HEAD or a changed tree is surfaced as STALE_HEAD / DIVERGENCE, never silently
reused.

Registration (example, .claude/settings.json):

```json
{"hooks": {"SessionStart": [{"hooks": [{"type": "command",
  "command": "python /absolute/path/hooks/session-start-context/run.py"}]}]}}
```

Boundary: restore/status only. No capture, no promotion, no policy.
