# ADR-0010 — Implementation Economy

- Status: accepted
- Date: 2026-09-06
- Constrains: `AGENTS.md`, `skills/implementation-economy/SKILL.md`,
  `skills/issue-to-implementation/SKILL.md`, `docs/GITHUB-WORKFLOW.md`,
  Implementation Economy qualification tests and evidence.
- Does not modify: ADR-0001 through ADR-0008. The Verified Work Plane's
  authority architecture remains closed and is consumed through its existing
  workflow rather than changed here.
- Related governance: GOV-ARCH-ENFORCEMENT (#38) established Case A: both Mavis mechanisms are machine-local and optional; portable enforcement is the manual discipline.

## Context

AI coding agents tend to overproduce implementation machinery: helpers,
wrappers, factories, interfaces, configuration, dependencies, persistent
state or extra files even where existing canonical behavior, a native
facility, the standard library or a small cohesive change satisfies the
complete accepted contract.

Optimizing for fewer lines is not a sufficient answer. A locally shorter
change can increase system complexity through wrong ownership, duplicated
policy, a new source of truth, or removed defensive behavior.

The repository already holds compatible principles: one authoritative
source per fact, cognitive load over short files, deep modules over empty
wrappers, ownership restoration, explicit Issue and Acceptance-Criteria
scope, fail-closed policy conflicts, and the Architectural Change
Discipline.

What is missing is one implementation-time procedure turning those
principles into a repeatable ownership-first sequence without another
runtime, persona, reviewer, global mode or scoring system. The method takes
inspiration from anti-overengineering ideas explored by
DietrichGebert/ponytail; the implementation stays first-party with no
imported runtime, persona, hook or mode.

## Decision

Add a first-party implementation discipline named **Implementation Economy**.

Its invariant is:

> Build everything the accepted system needs, and nothing it does not. At the
> correct ownership boundary, prefer the least new accidental complexity that
> fully preserves accepted behavior and engineering invariants.

Implementation Economy applies only to implementation choices after accepted
scope is established, never to requirements, architecture or work authority.

### 1. Separate WHAT from WHERE

**WHAT** is the accepted behavior: Issue, Acceptance Criteria, approved
scope changes and Work Contract where policy requires one. A direct
instruction clarifies scope only as the workflow permits; it never
bypasses Issue persistence, claim, AC binding, approval or contract.
Economy cannot weaken, reinterpret, replace or expand WHAT.

**WHERE** is the responsibility owner, established from applicable policy,
ADRs and contracts, canonical interfaces, current ownership, consumers
and dependency evidence. Economy helps discover WHERE; it never creates
authority.

### 2. Policy conflicts fail closed

There is no generic `AGENTS.md > ADR` or `ADR > AGENTS.md` precedence rule.
Different authorities govern different domains.

A real contradiction is `POLICY_CONFLICT`: stop the affected work, surface the
exact conflict and reconcile it through the existing repository workflow.

### 3. Hard Boundaries

No Economy decision may weaken an applicable:

- accepted scope or Acceptance Criterion;
- repository policy or architectural contract;
- public contract;
- correctness or error semantic;
- authentication, authorization, validation or trust boundary;
- data-integrity, transaction or idempotency guarantee;
- concurrency semantic;
- timeout, cleanup, cancellation or required backpressure behavior;
- compatibility guarantee;
- required performance, latency or resource budget;
- observability or audit requirement;
- accessibility requirement;
- required verification;
- migration, recovery or rollback guarantee.

A smaller implementation is worse if it regresses any Hard Boundary.

### 4. Ownership precedes economy

Correct ownership is a validity condition, not an optimization metric:

```text
accepted behavior
    -> correct owner
    -> implementation mechanism
    -> economy comparison
```

A new ownership boundary established as architecturally necessary must be
created. Economy may optimize only inside or between ownership-valid designs.

### 5. Ownership Evidence Search

Consult applicable repository and local policy, ADRs and architecture
contracts, module documentation, canonical interfaces, current callers
and consumers, existing ownership and dependency evidence. This is a
search strategy, not an authority ladder: contradictory authoritative
sources produce POLICY_CONFLICT, and shared policy with no establishable
authoritative owner is surfaced, never duplicated.

### 6. Architectural changes delegate to the existing discipline

Implementation Economy does not create a parallel architectural checklist.

For changes covered by the repository's Architectural Change Discipline, follow
that discipline, including the currently documented mandatory manual evidence:
`graphify path <symbol>`, direct reading of at least three call sites, and an
explicit statement of affected/unaffected scope.

GOV-ARCH-ENFORCEMENT (#38) established Case A: `pretool-arch-change-detect`
and `arch-change-gate` exist only in the maintainer's machine-local Mavis
setup; they are harness-specific and optional, never public distribution.
Portable enforcement is the manual discipline above, and
`hooks/pretool-graphify-inject/` is public source-only with manual
per-harness installation. Economy delegates to that portable discipline and
repairs nothing opportunistically.

### 7. Minimal New Footprint

After correct ownership and every Hard Boundary are satisfied, compare otherwise
valid alternatives lexicographically by new footprint:

1. new ownership boundary;
2. new source of truth;
3. new persistent state / persistence mechanism;
4. new public surface;
5. new configuration surface;
6. new dependency;
7. new abstraction;
8. new source file;
9. LOC.

The first item does not authorize avoiding a required owner. A new ownership
boundary proven architecturally necessary is already a validity requirement and
is not a cost Economy may optimize away.

This is a tie-breaker, not a weighted score, budget or target.

### 8. Legitimate abstractions

A new abstraction is legitimate with at least one real reason: multiple real
consumers, accepted architecture or ADR, a real trust or system boundary,
isolation of a volatile external dependency, a stable compatibility
adapter, a real test seam, substantial hidden complexity behind a stable
interface, or a required instrumentation or platform boundary.

A single consumer is neither proof of necessity nor proof of overengineering.

### 9. Residual Novelty Gate

Architectural-change discipline remains canonical. Economy asks a short residual
question only for additions not already governed there:

- **new dependency** — why cannot stdlib/native/already-approved dependency
  satisfy the complete contract?
- **new configuration surface** — what real supported variability requires it?
- **new source of truth/persistence** — why cannot existing canonical state own
  or derive the information?
- **new execution/lifecycle mechanism** — which accepted behavior requires a new
  worker, queue, scheduler, retry subsystem, cache, background process, event
  bus or lifecycle service?

If triggered, record one concise Novelty rationale in the existing summary
with no new artifact; a trigger on a trivial task re-runs proportionality.

### 10. Focused verification and one simplification pass

For applicable non-trivial work:
```text
implement
-> smallest relevant focused verification
-> ONE scoped simplification pass
-> same focused verification
-> normal repository gates
```

Focused verification is the smallest test, type, lint or contract check
capable of detecting a regression in the local change; it is not the full
repository suite run twice. The pass covers only newly introduced code
plus pre-existing code whose semantics necessarily change for the accepted
work. It removes new complexity without changing semantics, ownership,
Hard Boundaries or verification; moving complexity elsewhere is not a
valid simplification. Where the pass breaks relevant verification, revert
the simplification rather than weakening the contract or test.

### 11. Scope Firewall and Boy Scout behavior

Implementation Economy never widens explicitly scoped work.

```text
accepted explicit scope
    > Implementation Economy
    > opportunistic cleanup
```

Cleanup joins the current change only when directly necessary for accepted work.

The repository's Boy Scout wording is changed to preserve this invariant:
touched code may be left cleaner when that cleanup belongs to accepted work;
unrelated neighbouring debt follows normal triage rather than entering a scoped
PR merely because it is quick.

Mechanical proof that code is dead establishes deletion **safety**, not
permission to widen scope.

### 12. Pre-existing deletion fails closed

Never delete pre-existing code only because grep, a call graph, an LLM or local
tests found no caller.

Deletion requires either:

A. accepted scope explicitly includes removal; or

B. the relevant reachability domain is mechanically closed and the removal is
otherwise inside scope.

Evidence for B includes private or non-exported symbols, mechanically
enumerable consumers, absence of registration, string or config dispatch,
closed language and framework dispatch semantics, deterministic dead-code
tooling and relevant verification. Configuration, hooks, CI workflows, CLI
entry points, plugin registries, reflection, dynamic imports,
callbacks and events, serializers, routes, frontmatter, templates,
FFI and exported symbols, public APIs, string dispatch and DI registries
all defeat a naive static caller search; the list is illustrative, and
absence from it never proves reachability closed. Where closed
reachability cannot be established, retain the pre-existing behavior and
route suspected debt through normal triage when worth retaining.

### 13. Verified Work Plane interaction

Implementation Economy does not modify the Verified Work Plane authority rules
defined by ADR-0001 through ADR-0008.

The Work Plane already fails closed on freshness states such as
STALE_CONTRACT, STALE_SCOPE and STALE_DEPENDENCY. A contract bound before
Phase D can still legitimately change bound implementation paths when
ownership analysis establishes another canonical owner. Whenever
implementation or simplification changes bound paths, covered paths or
verification coverage, reconcile through the canonical Verified Work Plane
workflow, re-run relevant verification and restore CONVERGED where policy
requires it. Never edit authority artifacts ad hoc.

### 14. Sources of truth

ADR-0010 records the decision and invariants; skills/implementation-economy
carries the live procedure; AGENTS.md carries only a minimal pointer and
the scoped Boy Scout rule; issue-to-implementation cross-references
Economy in Phase D without copying it; GITHUB-WORKFLOW lists the skill
descriptively. A semantic change to Hard Boundaries, ownership-first
semantics, the Minimal New Footprint order, Scope Firewall or deletion
safety requires the normal ADR amend or supersede process plus the
matching skill update in the same change set. No synchronizer exists.

### 15. Applicability

The skill description and body carry the same exclusions. Apply the
Economy optimization rules after scope is established during code
generation, bug fixing, feature implementation and scoped refactoring.
Never apply them to requirements definition, planning, architecture
design, architecture review, security review, code review, audit or
research. Where a harness cannot load the skill, fall back to existing
design-complexity, architecture, security and verification policy; do not
duplicate the procedure into AGENTS.md for harness compatibility.

### 16. Distribution

The first-party skill lives under skills/implementation-economy/SKILL.md
so existing generic discovery exposes it. PR-IE-1B2 adds a generic
temporary-HOME regression proving the machine installer exposes every
generic skill to the shared skill roots; the test protects the mechanism
as a whole and special-cases nothing for Economy.

### 17. Qualification

Deterministic CI and behavioral qualification are separate.

Deterministic CI takes no model or network dependency. It validates the
skill, frontmatter and applicability contract, the workflow
cross-reference, fixture schema with explicit AC, family and
classification metadata, expected hard-gate metadata, and corpus
non-vacuity with an explicit expected case count. A green run with zero
discovered cases is failure. Fixture families, edge cases and loader
mechanics are defined by PR-IE-2A, not by this ADR.

Behavioral qualification uses real target harness and model combinations
in reproducible manual runs across OVERBUILD, UNDERBUILD, OWNERSHIP,
NOVELTY and SCOPE families. Case design and harness mechanics are defined
by PR-IE-2B. It must also prove Economy stays inactive for requirements,
planning, architecture design and review, security review, code review,
audit and research, including implementation-to-review session transitions
where the harness supports persistent sessions.

Hard gates come before any secondary complexity metric:
- AC regressions = 0;
- scope regressions = 0;
- security regressions = 0;
- architecture regressions = 0;
- data-integrity regressions = 0;
- required-verification regressions = 0;
- Economy bias on excluded tasks = 0;
- reviewer independence = PASS or legitimate N/A.
N/A is permitted only where the harness demonstrably lacks the required
persistent-session capability, and the evidence records that limitation.

Any attributable hard regression is NO-GO.
Ambiguous architecture evaluation uses an arm-blinded rubric with human
adjudication or is excluded from quantitative comparison; no single LLM
judge is ever the sole authority for a security hard-gate verdict.

Baseline and treatment use separate method roots, HOME and config,
workspaces and processes, with byte-identical task trees; only explicitly
allowlisted methodology surfaces may differ. Any non-allowlisted
difference classifies the run INVALID_EXPERIMENT, never a model result.
Runs record task-tree and method digests, versions and result metadata as
committed historical evidence.

### 18. Anti-Debt stays independent

Core Economy adds no Anti-Debt category, scanner or Critic contract.
Candidate future smells stay evidence-gated, never pre-approved. The
free-form subcategory schema question is separate governance work.

### 19. Future enforcement is evidence-gated

Deterministic structural enforcement arrives only after behavioral
evidence shows a repeated, critical, credibly detectable pattern. It must
not add another hardcoded threshold consumer before GOV-COMPLEXITY-SOURCE
reconciles the checker with the canonical numeric configuration.

## Rejected alternatives

**Use Ponytail directly.** An external persona and runtime would add a parallel source of engineering policy; rejected.

**Optimize for shortest diff or fewest LOC.** Local compactness can move policy to the wrong owner or remove necessary safeguards; rejected.

**Add an Economy runtime mode or environment flag.** Global mode semantics for what is only an implementation procedure; rejected.

**Add find_owner.py.** Architectural ownership is evidence-backed judgment, not reliably computable from file structure; rejected.

**Add verify_scope.py from a list of Issue files.** Work scope is a behavioral contract, not a canonical path whitelist; rejected.

**Add an Economy Reviewer.** An independent existing reviewer is preferable to another reviewer biased toward minimalism; rejected.

**Add a permanent PR Novelty checkbox matrix.** It duplicates architecture governance and creates bureaucracy even when no novelty exists; rejected.

**Require Docker for qualification.** Isolated method roots, HOME, workspaces and processes are the more portable boundary; rejected.

**Modify Anti-Debt immediately.** Prevention and debt detection are separate concerns that require evidence first; rejected.

## Consequences

Positive: agents get an ownership-first anti-overengineering procedure;
smaller wins only after correctness and ownership are proven; required
abstractions, controls and safeguards survive simplification pressure;
explicit scope is strengthened, not widened; deletion is conservative and
fail-closed with no new runtime, mode, dependency or state, and
qualification also proves planning and review work stays unbiased.

Costs: one more skill to learn; some suspected-dead code intentionally
remains until removal is explicitly scoped or reachability is mechanically
closed; behavioral qualification needs external paired harness/model runs;
GOV-ARCH-ENFORCEMENT (#38) concluded Case A at acceptance time.

## Rollback

The operational integration reverses as a coherent set: remove the AGENTS
pointer and scoped Boy Scout wording, remove skills/implementation-economy,
remove Phase-D and workflow cross-references, and remove Economy-specific
contract and qualification tests where no longer useful, with no database,
persistent Economy state or user-data migration. If abandoned, this ADR is
superseded or rejected per repository ADR policy, never silently deleted.

## Provenance

Inspired in part by anti-overengineering principles explored by
DietrichGebert/ponytail; no Ponytail runtime, persona, hook or mode is adopted, and the method stays first-party.
