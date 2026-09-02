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

## Practical consequence

Changing `src/auth/token.ts` after a verification that scoped it invalidates the run.
Changing an unrelated README does not. Changing a declared dependency such as
`pyproject.toml` does, even where no scoped source file changed.
