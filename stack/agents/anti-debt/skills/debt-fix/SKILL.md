---
name: debt-fix
description: Fix a specific finding in dry-run mode + mandatory human validation. Produce patches ready for PR.
license: MIT
---

# Skill: debt-fix

## NON-NEGOTIABLE guardrails

### Mandatory pipeline
```
Fix
 ↓
Patch (unified diff)
 ↓
Associated test (TDD: test first)
 ↓
Local validation (lint + tests + scope)
 ↓
Critic Engine (re-evaluate)
 ↓
Pull Request
 ↓
Human validation (MANDATORY)
 ↓
Merge
```

### Prohibitions
- ❌ Never automatic commit without human validation
- ❌ Never automatic merge
- ❌ Never fix outside the user's whitelist
- ❌ Never fix without an associated test
- ❌ Never fix that creates debt (validated by Critic)

## Workflow
1. Read the targeted finding and its evidence
2. Understand the context (read adjacent code)
3. Write the test BEFORE the fix (TDD)
4. Write the minimal fix
5. Run tests: must pass
6. Run the Critic: must validate
7. Produce a unified diff
8. **WAIT for explicit "apply"** from the human

## What I produce
- `fix-<id>.patch` : unified diff
- `fix-<id>.test.patch` : associated test
- `fix-<id>.rollback.md` : rollback procedure
- PR ready for review (never automatically merged)

## Dry-run mode

By default, this skill operates in dry-run mode. The patches are produced
but never applied to the user's tree. The user must explicitly say:

```
apply fix-<id>
```

to trigger the application.
