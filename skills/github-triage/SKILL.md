---
name: github-triage
description: |
  Turn ideas, bugs, findings and audit observations into clean GitHub backlog
  entries — or correctly refuse to. Triage is a decision procedure, not a
  writing exercise: most candidates should NOT become Issues.

  Decides between: GitHub Issue, Discussion, ADR candidate, and reject. Never
  implements code while running. AI-generated findings are candidates, not
  automatically backlog.

  Use when: "triage", "file an issue", "should this be an issue",
  "clean up findings", "classify this bug", "audit follow-up".
origin: ai-native-dev-stack
---

# /github-triage — findings to clean backlog entries

Purpose: turn ideas, bugs, findings and audit observations into clean GitHub
backlog entries — persisting only useful work, and stopping there.

**Never implement code while running this skill.** Triage ends at the backlog
decision. Implementation belongs to `/issue-to-implementation` on a claimed
Issue.

---

## Workflow

1. **Understand the finding.** Restate it in one sentence a maintainer could
   act on. If you cannot, it is not ready for triage.
2. **Validate or reproduce when applicable.** A bug that does not reproduce
   and cannot be reasoned to a root cause is a research candidate, not a
   `type:bug`.
3. **Search existing Issues** (open and recently closed) before anything else.
4. **Detect duplicates.** An existing Issue that already covers the finding:
   add a comment with new evidence (only if it adds information), otherwise
   drop the finding. Never open a parallel Issue for the same root cause.
5. **Group same-root-cause findings.** One root cause, one Issue; secondary
   symptoms go in its body, not in sibling Issues.
6. **Determine actionability.** "Someone should decide X" and "investigate
   whether X is possible" are different animals (Issue vs research).
7. **Classify type:** `type:bug` | `type:feature` | `type:docs` |
   `type:security` | `type:research`.
8. **Classify priority:**
   - `priority:P0` — broken core, security hole, data loss; blocks release.
   - `priority:P1` — serious defect or gap with a concrete reproducible cost.
   - `priority:P2` — real improvement, not urgent.
   - `priority:P3` — nice-to-have, research, or speculative.
9. **Decide the destination:**
   - **Issue** — actionable, specific, worth a maintainer's queue slot.
   - **Discussion** — needs community input before it can be scoped.
   - **ADR candidate** — an architecture decision is being proposed (issues
     record work; ADRs record accepted decisions — see docs/GITHUB-WORKFLOW.md).
   - **Reject / not planned** — explicitly declined; say so in one sentence.
     Do not create an Issue for rejected work "for the record".
10. **Persist only useful work** — the Issue(s) (or Discussion/ADR candidate
    note), with labels, and nothing else. No mirrors in files, no vault board
    entries for active state.
11. **STOP.** Report what was created, what was dropped, and why.

---

## Escalation rules

```text
P0/P1 validated  -> may create/escalate an Issue if authorized
P2 actionable    -> may create an Issue if useful
P3 / research    -> do not automatically create
```

"Authorized" means the operator asked for triage, or repository policy lets
you file P0/P1 directly. When in doubt, present the candidate Issue (title,
body sketch, type, priority) and wait for approval instead of filing.

P3/research findings go to the requester as prose (or a Discussion when one
exists). They are not automatically converted into Issues — that is how a
backlog rots.

---

## Issue quality bar

A filed Issue uses the repository's templates (bug / feature) and contains:

- A **Problem** section stating the observable defect or gap, not the fix.
- **Expected outcome** stated as behavior.
- **Acceptance criteria** as a checklist — the implementation agent will be
  bound to these; write them like a contract (see the AC protection rules in
  docs/GITHUB-WORKFLOW.md).
- Labels: one `type:*`, one `priority:*`, plus `good first issue` / `help
  wanted` when genuinely appropriate.
- Milestone only when delivery grouping is real, not aspirational.

Never create Project fields for type or priority, never create `area:*`
labels (Area is Project metadata, when a Project exists at all), and never
require a Project — a small repository works with Issues, labels and PRs
alone.

---

## Anti-patterns

- Filing one Issue per symptom of a single root cause.
- "P3 shotgun": filing every idea because storage is free. A backlog is a
  queue with trust, not a notebook.
- Escalating priority to get attention.
- Implementing "just a small fix" while triaging — that is scope smuggling
  without a claim, an AC, or a review.
- Silently re-classifying an existing maintainer decision (a closed
  not-planned Issue stays closed unless a maintainer reopens it).