# postedit-staleness (PostEdit / PostTool)

Re-evaluates dependency staleness after edits. Pure read: signals only, no
rewrites, no review candidates are created here.

Registration (example, .claude/settings.json):

```json
{"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": [{"type": "command",
  "command": "python /absolute/path/hooks/postedit-staleness/run.py"}]}]}}
```

Boundary: staleness/freshness only. No mutation of any kind.
