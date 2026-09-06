---
name: implementation-economy
description: |
  Apply during code generation, bug fixing, feature implementation and
  scoped refactoring after accepted scope has been established. Minimize
  accidental new complexity only after correct ownership and engineering
  invariants are preserved.

  Do not apply to requirements definition, planning, architecture design,
  architecture review, security review, code review, audit or research.
origin: ai-native-dev-stack
---

# /implementation-economy

## STOP — applicability check

Apply this skill only to implementation choices made after accepted scope
exists: code generation, bug fixing, feature implementation and scoped
refactoring.

Never apply it to requirements definition, planning, architecture design,
architecture review, security review, code review, audit or research. A
review that starts recommending less architecture, fewer controls or less
testing because this skill exists is contaminated: stop and fall back to
the review discipline.

## 1. Bind the accepted contract

Read the accepted scope, the Acceptance Criteria and every applicable Hard
Boundary (ADR-0010, section 3), plus the applicable policy. Implementation
Economy never weakens, reinterprets, replaces or expands accepted behavior.
A real policy contradiction is POLICY_CONFLICT: stop the affected work,
surface it and reconcile through the repository workflow. Never choose
silently.

Verify no regression in: accepted scope and Criteria; policy and public
contracts; correctness and error semantics; authentication, authorization,
validation and trust boundaries; data integrity, transactions and
idempotency; concurrency; timeouts, cleanup, cancellation and backpressure;
compatibility; performance budgets; observability and audit; accessibility;
required verification; migration, recovery and rollback. A smaller change
that regresses any of these is worse, never an economy.

## 2. Establish the correct owner before any mechanism

Correct ownership is a validity condition, never an optimization metric.
Search the applicable evidence: repository and local policy, ADRs and
contracts, canonical interfaces, current callers and consumers, existing
ownership and dependency evidence. Keep the canonical owner for shared
policy. Where no authoritative owner can be established and the change
would duplicate shared policy, surface the ambiguity instead of inventing
a second copy.

Fixed sequence: accepted behavior -> correct owner -> implementation
mechanism -> economy comparison. Never choose the convenient owner first.

## 3. Reuse required behavior before inventing

Ask in order: does required behavior already exist? Can existing canonical
behavior be reused? Can the standard library or native facilities satisfy
the complete contract? Can an already-approved dependency? Only then
consider a new abstraction.

## 4. Compare ownership-valid mechanisms only

Compare otherwise valid alternatives by new footprint, in this exact order
(ADR-0010, section 7):

1. new ownership boundary;
2. new source of truth;
3. new persistent state / persistence mechanism;
4. new public surface;
5. new configuration surface;
6. new dependency;
7. new abstraction;
8. new source file;
9. LOC.

This is a tie-breaker, never a score, budget or target. A new ownership
boundary proven architecturally necessary is a validity requirement: a
required owner is never a cost Economy may optimize away.

## 5. Accept legitimate abstractions

A new abstraction is legitimate with at least one real reason: multiple
real consumers, accepted architecture or ADR, a real trust or system
boundary, isolation of a volatile external dependency, a stable
compatibility adapter, a real test seam, substantial hidden complexity
behind a stable interface, or a required instrumentation or platform
boundary. A single consumer is neither proof of necessity nor proof of
overengineering.

## 6. Apply the residual Novelty Gate

Architecture discipline stays canonical. Ask only what it does not already
govern:

- new dependency: why can stdlib, native or approved dependencies not
  satisfy the complete contract?
- new configuration surface: what real supported variability requires it?
- new source of truth or persistence: why can existing canonical state not
  own or derive the information?
- new execution or lifecycle mechanism: which accepted behavior requires a
  new worker, queue, scheduler, retry subsystem, cache, background process,
  event bus or lifecycle service?

Record one concise `Novelty:` rationale in the existing summary when
triggered, never a new artifact. A trigger on a trivial task re-runs the
existing proportionality decision.

## 7. Implement the cohesive solution

Write the change cohesively at the established owner, preserving every
Hard Boundary and the bound verification.

## 8. Run focused verification

The smallest test, type, lint or contract check able to detect a regression
in the local change. Never the full suite twice.

## 9. Take ONE scoped simplification pass

Cover only newly introduced code plus pre-existing code whose semantics
necessarily change for the accepted work. Remove new complexity without
changing semantics, ownership, Hard Boundaries or verification, then run
the same focused verification again. Moving complexity elsewhere is not
simplification. When the pass breaks verification, revert the
simplification; never weaken the contract or the test.

## 10. Respect the Scope Firewall

Accepted explicit scope outranks Economy, which outranks opportunistic
cleanup. Cleanup joins the change only when directly necessary for the
accepted work. Mechanical proof that code is dead establishes deletion
safety, never permission to widen scope.

## 11. Keep pre-existing deletion fail-closed

Never delete pre-existing code on a grep, call graph, model opinion or
green local run alone. Deletion needs explicit removal scope, or in-scope
removal plus mechanically closed reachability. Configuration, hooks, CI
workflows, CLI string dispatch, plugin registries, reflection, dynamic
imports, callbacks and events, serializers, routes, templates and
frontmatter, FFI and exported symbols, public APIs, string dispatch and DI
registries defeat a naive static caller search; the list is illustrative,
never exhaustive. Otherwise keep the code and route suspected debt through
normal triage.

## 12. Reconcile the Work Contract when required

When implementation or simplification changes bound implementation paths,
covered paths or verification coverage, reconcile through the canonical
Verified Work Plane workflow and re-run the relevant verification. Never
edit authority artifacts ad hoc.

## 13. Run the normal repository gates

