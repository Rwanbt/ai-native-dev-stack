---
name: debt-verify
description: Verify that a fix resolved the finding without introducing regression.
license: MIT
---

# Skill: debt-verify

## When to use me
- After applying a fix
- Before a merge (checklist)
- Periodically (incremental re-scan)

## What I verify
1. The original finding is resolved (re-detection: must return 0)
2. No regression (all tests pass)
3. No new debt introduced (incremental re-scan)
4. The fix is in the authorized whitelist
5. Critic Engine validates again

## What I produce
- `verify-<id>.json` : structured report
- Update of `.debt-history.json`:
  - Finding marked `resolved`
  - If regression detected: `regressed`

## Anti-gaming verification

To prevent an agent from "resolving" a finding by modifying code to make the
detector silent (without actually fixing the problem):

- Re-run the SAME detectors that produced the finding
- Re-run the OPPOSITE detectors (e.g. if a fix removes complexity, re-test that
  functionality still works)
- Human review is MANDATORY for `critical` and `high` severity fixes
- Diff must be human-readable and reviewed before merge

## Report format

```json
{
  "verify_id": "v-2026-06-17-001",
  "finding_id": "f-001",
  "timestamp": "2026-06-17T15:00:00Z",
  "finding_resolved": true,
  "tests_passed": true,
  "regressions_detected": [],
  "new_debt_introduced": [],
  "human_review_status": "pending | approved | rejected",
  "critic_validation": { ... }
}
```
