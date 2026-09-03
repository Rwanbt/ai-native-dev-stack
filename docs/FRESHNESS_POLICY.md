# Verified Work Plane V2 — Freshness Policy

## Scope

A verification result is valid only for the repository state it observed. The snapshot
records the HEAD commit, dirty state, scoped paths, declared dependencies, policy digest,
command-registry digest, and a canonical content digest.

## Freshness outcomes

| Outcome | Condition | Effect on convergence |
| --- | --- | --- |
| `FRESH` | Scope, dependencies, registry, policy, and relevant contract revision match | Eligible evidence |
| `STALE_SCOPE` | A verified scoped file changed | Blocking; rerun relevant verification |
| `STALE_DEPENDENCY` | A declared dependency changed | Blocking; rerun relevant verification |
| `STALE_REPO` | Repository changed outside declared scope and dependencies | Warning or information; does not force a full rerun |
| `COMMAND_REGISTRY_CHANGED` | Registered command definition differs from its approved baseline | Blocking; result cannot be presented as approved |
| `POLICY_CHANGED` | Project policy digest differs from the snapshot baseline | Blocking; re-evaluate convergence under the new policy |
| `ROOT_OF_TRUST_CHANGED` | The approval root the evidence bound is not the current one | Blocking; authority must be re-established |
| `VERIFICATION_SPEC_CHANGED` | The verification specification the evidence bound was rewritten | Blocking; the run no longer describes what is now required |
| `STALE_CONTRACT` | The work contract digest moved under the evidence | Blocking; the run describes an earlier contract |
| `FRESHNESS_UNAVAILABLE` | No freshness evaluation was supplied | `INVALID`; absence of evaluation is never freshness |

## Canonicalisation rules

- Paths are repository-relative, use `/`, and contain neither a `.` nor `..` path
  component; names such as `.well-known` remain valid. Paths cannot resolve outside the
  repository.
- Case-distinct paths that collide on a case-insensitive filesystem are rejected; they
  are never silently merged.
- Regular files, including binaries, are hashed as bytes with full SHA-256.
- Large files use streaming SHA-256 unless an explicit future policy excludes them.
- FIFOs, sockets, devices, and escaping symlinks are security rejections, not files
  that may be silently skipped.
- Normative JSON uses UTF-8, sorted object keys, fixed separators, and a documented
  Unicode policy before SHA-256 is calculated.

## What freshness still decides

Since the authoritative evaluator executes the verifications it judges,
evidence is always current for a still checkout: staleness relative to the
repository is no longer how a stale result gets caught, because a stale result
is no longer reused. What the freshness engine still decides is:

- a checkout that moves *underneath* a running verification (`STALE_SCOPE`,
  `STALE_DEPENDENCY`) — a race, and the reason A57 exists;
- evidence bound to a contract, specification, registry, policy or root other
  than the one in force, which is a binding failure rather than an age one.

Said plainly rather than left for a reader to infer from a green suite.

## Where freshness comes from

The authoritative evaluator recomputes freshness from the checkout, once per
verification specification, using that specification's `execution_scope` as the
snapshot scope and its `covered_implementation_paths` as the dependency set. It
accepts no current-identity fixture from a caller, and it never derives one
run's freshness from another's. `evaluate_freshness` remains available as a
pure function for tests; it is not the production path.

## Practical consequence

Changing `src/auth/token.ts` after a verification that scoped it invalidates the run.
Changing an unrelated README does not — it yields `STALE_REPO`, which is outside
`BLOCKING_FRESHNESS` by design. Changing a declared dependency such as
`pyproject.toml` does invalidate, even where no scoped source file changed.

Every outcome in the table above is emitted by `ainative_workplane/freshness.py`
and asserted in `tests/test_workplane_adversarial.py` (cases A21-A28).
