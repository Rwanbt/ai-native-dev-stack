---
name: issue-to-implementation
description: |
  The primary implementation workflow: from a GitHub Issue to a merged PR,
  without ever widening the Issue's scope or bending its Acceptance
  Criteria to make the implementation pass.

  Enforces: visible claim before work, canonical scope, AC protection,
  policy-conflict surfacing, Refs-while-working / Closes-when-ready,
  MERGE_READY as a checklist, FINAL_MERGE_FRESHNESS immediately before the
  merge, and DONE only as "closed as completed" after the merge.

  Use when: "implement this issue", "work on #N", "claim the issue",
  "open the PR for #N", "merge ready check", "finish this issue".
origin: ai-native-dev-stack
---

# /issue-to-implementation — from claimed Issue to merged PR

One skill owns the whole path. The thirty-plus steps below are the contract;
internally you run them as one continuous procedure — no human needs to tick
them one by one, but none may be skipped.

**Never modify an Issue's Acceptance Criteria to make your implementation
pass.** That rule has no exception inside this skill; see "AC protection".

---

## Phase A — Read before acting

1. **Read the Issue** — body, comments, labels, milestone, linked PRs.
2. **Read the root `AGENTS.md`** of the repository.
3. **Read applicable local `AGENTS.md`** files for every directory you will
   touch.
4. **Read relevant ADRs** (the Issue or the code will point at them).
5. **Detect policy conflicts.** A local policy may specialize, strengthen or
   add constraints; it must never silently weaken the root policy. If a real
   contradiction exists: `POLICY_CONFLICT` — stop affected work, and when
   working from an Issue post a concise comment stating the conflicting
   files, the conflicting rules, and why implementation cannot proceed
   safely. Never silently choose one policy. ADRs and AGENTS.md govern
   different domains; a contradiction between them also requires
   reconciliation, not arbitrary precedence.
6. **Inspect the implementation context** — the code, its tests, its callers.

## Phase B — Claim

7. **Read the claim state:** assignees, existing claim comments, open linked
   PRs.
8. **Attempt a visible claim:** GitHub Issue assignment if you can; otherwise
   an explicit comment ("Claiming this Issue for implementation.").
9. **Re-read the claim state** after claiming. A claim is only as good as the
   freshest read.
10. **Resolve deterministically** with
    `skills/issue-to-implementation/bin/claim_resolution.py` (no lock service
    exists; GitHub state is the claim):
    - `0` valid claims -> `CLAIM_FAILED` -> STOP.
    - `1` valid claim -> claimant proceeds.
    - `>1` -> sort by `created_at` ascending, then stable GitHub identifier
      ascending; first = winner; all losers STOP.
    - ordering indeterminate -> `CLAIM_CONFLICT` -> every claimant STOPs.
11. **If you are not the winner: STOP.** Do not "help", do not open a
    parallel PR.

## Phase C — Scope

12. **Establish the current Issue scope and Acceptance Criteria.** The AC is
    the checklist in the Issue body — there is no separate AC database.
13. **Bind the AC:** record the canonical AC digest
    (`bin/ac_guard.py --bind`; content-addressed, checkbox-state independent)
    in the session notes and, for Verified work, in the Work Contract.
14. **You MUST NOT modify material AC without authorized approval.** Material
    means: required behavior, functional scope, security requirement,
    performance threshold, supported platform, failure behavior, public
    API/contract, acceptance threshold. You MAY detect ambiguity, identify
    infeasibility, propose a change, request clarification. A material change
    becomes authoritative only after explicit maintainer/user approval AND
    persistence in the GitHub Issue. If uncertain whether a change is
    material: treat it as material and ask.
15. **Create the implementation branch** (`feat/123-description`,
    `fix/123-description`, ...).
16. **Create or update the Work Contract if repository policy requires it**
    (Verified profile), binding the AC digest from step 13.

## Phase D — Implement

17. **Implement only the canonical Issue scope.** Unrelated findings are not
    yours to fix in this PR (P0/P1: separate Issue/escalation; P2/P3:
    backlog candidate).
18. **Run the required validation** — the repository's own gates, plus the
    Issue's AC as executable checks wherever possible.

## Phase E — PR

19. **Open or update the PR with `Refs #N`** — never `Closes` yet.
20. **Re-read the current Issue.**
21. **Revalidate the current Acceptance Criteria** against what you
    implemented (and against your bound digest for Verified work).
22. **If the AC drifted: `ISSUE_CHANGED`, STOP.** Reconcile scope with the
    maintainer before continuing; do not merge, do not close.

## Phase F — MERGE_READY

23. **Confirm every MERGE_READY condition:**
    - current Issue AC satisfied;
    - required tests/checks pass;
    - documentation updated where required;
    - review requirements satisfied;
    - no relevant blocker;
    - Verified CONVERGED when policy requires it;
    - Issue scope/AC freshness confirmed.
    MERGE_READY does NOT mean merged.

## Phase G — Close the loop

24. **Change `Refs #N` to `Closes #N`** in the PR body — only now.
25. **Immediately before the actual merge: FINAL_MERGE_FRESHNESS.** Re-read
    the Issue and its current AC (step 20-21 again, now at merge time).
26. **If anything material changed: invalidate MERGE_READY, `ISSUE_CHANGED`,
    STOP.** Do not merge, do not close; reconcile and verify again.
27. (Covered by 25-26 — freshness is the gate, not a formality. This is the
    freshest possible pre-merge check, not an atomic GitHub transaction.)

## Phase H — Merge and finish

28. **Merge only through the repository-authorized process.** Squash when the
    repository prefers it; never bypass review or CI requirements.
29. **Confirm the Issue closed as completed** (not as duplicate / not
    planned / invalid / superseded).
30. **If a Project exists:** set Project Status to `Done`.
31. **If the Project update is impossible (permissions):** report
    `PROJECT_STATUS_SYNC_REQUIRED` — visibly, not silently.
32. **Preserve the required verification/history** (Work Contract, run
    evidence, session summary with Issue/PR links).
33. **STOP.** The loop is closed. Any remaining findings go to
    `/github-triage`, not into the next PR by momentum.

---

## Non-negotiables (summary)

```text
- no work without a visible claim won deterministically
- no implementation outside the Issue's canonical scope
- no material AC change without authorized approval + persistence in the Issue
- no silent policy-conflict resolution
- Refs while working; Closes only at MERGE_READY
- FINAL_MERGE_FRESHNESS immediately before the merge, every merge
- DONE = merged + closed as completed (+ Project Done when configured)
- closed is not Done
```

## Helper tools (stdlib-only, no network)

- `bin/claim_resolution.py` — pure claim-resolution verdict from normalized
  claim signals (JSON in, JSON out).
- `bin/ac_guard.py` — extract the AC checklist from an Issue body, produce
  its canonical digest, check a bound digest for drift (`OK` /
  `ISSUE_CHANGED`).