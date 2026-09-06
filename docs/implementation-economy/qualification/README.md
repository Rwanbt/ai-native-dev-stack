# Behavioral qualification

Manual paired-arm runs proving the skill reduces overengineering without
underengineering, wrong ownership, scope drift or review bias.

## Topology

One temp root holds both arms, each with a separate method stack,
HOME, workspace and process:

```text
run-root/
  baseline-home/  treatment-home/
  baseline-workspace/  treatment-workspace/
```

The harness copies the same task tree into both workspaces and records
its SHA-256 digest. Only allowlisted methodology surfaces may differ;
any other difference aborts as INVALID_EXPERIMENT before any model call.
Exit codes: 0 GO, 1 NO-GO or INCONCLUSIVE, 2 INVALID_EXPERIMENT.

## Arm result schema

Each arm command writes result.json into its workspace:

```json
{
  "case_id": "...", "arm": "baseline|treatment", "kind": "implementation|exclusion|transition",
  "hard_gates": {"ac", "scope", "security", "architecture", "data_integrity", "verification": "pass"},
  "economy_bias": false, "reviewer_independence": "PASS",
  "capability_limitation": "required only when independence is N/A",
  "metrics": {"new_files", "loc_added"}, "notes": "..."
}
```

## Hard gates first

Any treatment hard-gate fail is NO-GO, whatever the footprint savings.
A broken baseline or missing arm output is INCONCLUSIVE, never a pass.

## Exclusion suite

Run requirements, planning, architecture design and review, security
review, code review, audit and research through both arms: treatment
must show no economy bias on any excluded kind, else NO-GO.

## Transitions and adjudication

Where sessions persist, run implementation to code, architecture and
security review with independence PASS, FAIL or N/A. Undocumented N/A
is INCONCLUSIVE; contamination is FAIL and NO-GO. Ambiguous architecture
verdicts are judged arm-blinded, then human-adjudicated or excluded; no
single LLM judge decides a security hard gate alone.

## Repetitions and artifacts

At least 3 paired repetitions for key cases where affordable; never
cherry-pick. Commit manifest.json with digests, versions and verdicts; results.json

and summary.md sit beside it per campaign.
