---
name: mvp-debt-report
description: Trace the debt introduced by an MVP explicitly requested. Transform involuntary debt into an informed choice.
license: MIT
---

# Skill: mvp-debt-report

## When to use me
- The user says "MVP", "V0", "quick & dirty", "ship fast"
- To formalize the accepted debt

## What I produce
- `.mvp-debt-report.md` : structured report

## MANDATORY structure

1. **Context** : why the MVP was chosen (quote the user)
2. **Shortcuts taken** : numbered list of everything that wasn't done
3. **Debt introduced** : findings classified by taxonomy category
4. **Immediate risks** : what MUST be fixed even in MVP (especially security)
5. **Resorption plan** : ordered by dependencies, estimated effort
6. **Tracking metrics** : how we know we've resorbed

## Rule

The MVP is acceptable ONLY if the debt report is produced.
No report = no MVP (the skill refuses).

## Example

```markdown
# MVP Debt Report — <Project>

**Date** : YYYY-MM-DD
**Status** : MVP debt explicitly accepted
**Scan source** : scan-...

## 1. Context

The user requested: "<quote>"

## 2. Shortcuts taken

1. ❌ No unit tests on ...
2. ❌ No input validation on ...
3. ...

## 3. Debt introduced

### Category `code`
- **f-mvp-001** : duplication (medium) — ...

### Category `security`
- **f-mvp-005** : unsafe_io (high) — ...

## 4. Immediate risks (MUST be fixed before production)

- **f-mvp-005** : ...

## 5. Resorption plan

| Action | Finding | Effort | Dependencies |
|--------|---------|--------|-------------|
| ... | ... | ... | ... |

## 6. Tracking metrics

- [ ] Coverage ≥ 80% on module X
- [ ] 0 findings `code.duplication`
- [ ] ...
```

See `examples/sample-mvp-debt-report.md` for a complete example.
