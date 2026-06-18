---
name: debt-plan
description: Transform the findings of a debt-scan into a prioritized, complete action plan. Produce `plan.json` conforming to the schema + a readable `plan.md`.
license: MIT
---

# Skill: debt-plan

## When to use me
- After a `debt-scan` validated by the Critic

## What I consume
- The DETERMINISTIC triage (`schemas/debt-triage.schema.json`, produced by
  `critic_v2.build_triage`): findings already sorted into accept/review/reject
  tiers by score. I turn that triage into a remediation plan that requires
  JUDGMENT — grouping findings into actions, justifying accepted debt.

## What I produce
- `plan.json` conforming to `schemas/debt-plan.schema.json` (DebtPlan — distinct
  from the triage: `actions` + `accepted_debt`, not raw tiers)
- `plan.md` readable summary

## NON-NEGOTIABLE rules

1. **Address 100% of critical/high findings** by default
2. **Medium findings**: either addressed or in `accepted_debt` with justification
3. **Low findings**: can be batched into "accepted debt" or backlog
4. **No simplification without explicit agreement** (anti-MVP)
5. **MVP explicit**: produce `.mvp-debt-report.md` in parallel (see `skills/mvp-debt-report/SKILL.md`)

## Plan structure

1. **Overview**: number of findings per category, total effort, average score
2. **Quick wins** (score > 10): low-effort + high-impact
3. **Structural refactors**: those that unblock the rest (dependencies)
4. **Prioritized backlog**: sorted by decreasing score
5. **Accepted debt**: `accepted_debt` findings with explicit justification
6. **Success metrics**: KPIs to measure progress

## MVP mode (triggered if the user says "MVP")

See `skills/mvp-debt-report/SKILL.md` for the parallel report structure.

## Before publishing (schema gate)

Validate the produced `plan.json` against its schema — judgment output is not
guaranteed to be well-formed:

```bash
python3 tools/validate_plan.py plan.json   # exit 0 = valid
```

Do not publish a plan that fails validation.

## Anti-MVP mechanisms

- The Critic MUST validate the plan before publication
- If `critic_validation.passed = false`, refuse to publish and address concerns
- If the user requests "completeness check" but the plan is incomplete → escalate
- Each action MUST cite the IDs of findings it addresses
- No action can be added without addressing at least one finding (or being justified)
