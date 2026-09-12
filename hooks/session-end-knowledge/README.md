# session-end-knowledge (SessionEnd)

Checkpoints the session and runs the advisory consolidation pass (read-only).
Claim capture stays an explicit agent/operator action: this adapter never
invents claims from a transcript.

Registration (example, .claude/settings.json):

```json
{"hooks": {"SessionEnd": [{"hooks": [{"type": "command",
  "command": "python /absolute/path/hooks/session-end-knowledge/run.py"}]}]}}
```

Boundary: checkpoint + advisory consolidation. No promotion, no canonical
mutation, no policy.
