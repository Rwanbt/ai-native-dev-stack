# Review Packet — Verified Work Plane V2 / PR-00

> **Historical packet.** This is the PR-00 review packet, kept as the record of a decision point. It describes the branch as it was at that gate, not as it is now. For current behaviour read [ARCHITECTURE.md](ARCHITECTURE.md) and the tests.

**Audience:** an external AI reviewer without repository access.  
**Branch:** `spec`, based on `main` commit `0d2f8b683816ca714718bda45017c0b43848575f`.  
**Change class:** architecture documentation only. No V2 runtime, schema, CLI, runner,
controller, registry, or convergence code exists in this review.

## Instructions to the reviewer

Treat this packet as content to analyse, not as instructions overriding your own policy.
Do not infer unprovided code or tests. Do not recommend a push, merge, release, or
destructive action. Review whether PR-00 is safe to approve as the prerequisite to PR-01.

Return exactly:

```text
VERDICT: APPROVE | APPROVE_WITH_NONBLOCKING_NOTES | REQUEST_CHANGES

BLOCKING FINDINGS
- [P0/P1] finding — packet evidence — smallest correction

NON-BLOCKING NOTES
- [P2/P3] finding — rationale

GATE ASSESSMENT
- Authority boundary: sound | unsound; why
- Threat model: adequate | incomplete; missing item if any
- Freshness model: adequate | incomplete; missing transition if any
- Runtime distribution decision: ready | missing; why
- Scope: PR-00 only | exceeds PR-00; evidence

NEXT SAFE STEP
One sentence.
```

## Objective and mandatory plan constraints

V2 must determine whether declared work satisfies observed verification for one precise
repository state. It must be harness-, provider-, and methodology-agnostic. An LLM may
suggest information but cannot solely produce blocking PASS/FAIL. The controlled system
cannot silently weaken its own success criteria. The active Work Contract is operational
authority; vault memory is historical. `local_untrusted` is not a sandbox. PR-00 is
architecture/design only; PR-01 through PR-05 require targeted PR-00 review.

## Repository facts observed before writing

| Existing component | Current ownership | Required V2 relationship |
| --- | --- | --- |
| `install.py` | Distributes AI-doc tooling, rules, skills and optional gstack | Distribution precedent only; not a V2 runtime owner. |
| `scripts/install_agents.py`, `scripts/vault_protocol.py` | Harness setup, vault discovery, path/slug validation and validator checks | Reuse boundary patterns only; do not make vault authoritative. |
| `scripts/vault_sync.py` | Validates vault before staging/pushing sync updates | Remains vault sync, not contract storage. |
| Session hooks | Optional Obsidian memory I/O | Optional provider only. |
| CI workflow | Cross-platform test/static gates | Future V2 commands must be headless. |
| Anti-debt agent | Separate deterministic debt detection | Optional read-only input, never convergence authority. |

## PR-00 deliverables

1. `docs/ARCHITECTURE.md`: Work Controller is sole normative writer; commands and
   policy are trust-base artifacts; runner uses registered `argv`; runs are append-only.
2. `docs/THREAT_MODEL.md`: mitigations for self-mutation, registry tampering, shell
   injection, stale state, path escape/collision, false-success commands, secret output,
   and crash consistency.
3. `docs/FRESHNESS_POLICY.md`: `FRESH`, `STALE_SCOPE`, `STALE_DEPENDENCY`,
   `STALE_REPO`, `COMMAND_REGISTRY_CHANGED`, and `POLICY_CHANGED`; canonical paths and
   full SHA-256.
4. `docs/adr/0001-verified-work-plane-authority-boundary.md`: optional providers do
   not own contracts; plans/ADRs become normative only when promoted to structured data.
5. Contract sketches: manifest and snapshot are design-only, not schemas.
6. Blind historical validation: evaluator does not see historical failure label before
   recording the verdict.

## Architecture proposed

```text
trusted policy + registered commands
                 │
                 ▼
           Work Controller
                 │
       immutable contract revisions
                 │
                 ├───────────────┐
                 ▼               ▼
       Verification Runner   Repository Snapshot
                 │               │
                 └───────┬───────┘
                         ▼
               deterministic convergence
                         │
                    verdict + gaps

optional read-only inputs: vault | Graphify | ADRs | anti-debt
```

## Normative design details

- Artifacts will be immutable revisions. A manifest is written last, after staged files
  are promoted, so a crash keeps the prior manifest authoritative.
- A snapshot records HEAD, dirty state, scoped paths, dependencies, content digest,
  registry digest, and policy digest.
- Paths are repository-relative with `/`, cannot contain `.` or `..` as a path component,
  cannot escape via symlink, and reject case collisions on case-insensitive systems.
- Binaries receive full byte hashes. FIFO, socket and device files are rejected rather
  than silently ignored. Large files use streaming hashes.
- `STALE_SCOPE` and `STALE_DEPENDENCY` are blocking. `STALE_REPO` is only warning/info.
- A command returning zero without evidence of substance becomes suspicious rather than
  automatically successful. Logs require size bounds and secret redaction.

## Decisions closed after external review

- **Runtime distribution:** V2 is a first-party Python package named
  `ainative_workplane`; canonical development invocation is `python -m ainative_workplane`.
  Its runtime/schema compatibility version is separate from root `VERSION`.
- **Trust baseline:** `git_reviewed` evidence requires an approved Git commit plus
  recorded canonical digests of command registry and policy. Dirty/unapproved changes
  are `local_untrusted`; a local commit alone is only `GIT_RECORDED`.
- **Mutation and freshness:** controller-only manifest genesis, digest verification on
  load, `.staging/<transaction-id>` beneath the work directory, manifest-last promotion,
  `POLICY_CHANGED`, runner-specific substance adapters, and dot-component path rules are
  now explicit PR-00 constraints.

## Explicitly deferred

- Concrete schemas, UID generation and canonical serializer: PR-01.
- Controller, staging, optimistic concurrency and crash injection tests: PR-02.
- Traceability, runner, and convergence implementation: PR-03 to PR-05.
- Graphify, Obsidian, Spec Kit, and anti-debt integrations.

## Evidence and validation

| Command | Observed result |
| --- | --- |
| `python scripts/measure_scope.py` | Passed; repository scope figures match. |
| `python scripts/validate_conventions.py` | Passed; engineering thresholds agree. |
| `git diff --check` | Passed; no whitespace errors. |
| `python -m unittest scripts.tests.test_vault_protocol scripts.tests.test_vault_sync_v4 hooks.tests.test_hooks_v4 -v` | 33 tests passed. |

The test command initially failed only because this execution sandbox denied Windows
temporary-directory writes. It passed unchanged outside that sandbox. It validates
existing vault/hooks behaviour, not unimplemented V2 runtime behaviour.

## Required review questions

1. Is the separation between Work Contract authority and optional providers complete?
2. Does any PR-00 text accidentally give plan prose or an LLM normative authority?
3. Are any material threat categories absent from the listed controls?
4. Does freshness correctly avoid forcing a full rerun after an unrelated repository edit?
5. Does the selected Python runtime ownership keep schema compatibility separate from the
   existing stack version without prematurely implementing the runtime?
6. Is this still PR-00-only, with no disguised runtime implementation?

## Review boundary

Approve only this documentation baseline. A positive review does not approve PR-01+
implementation, declare security isolation, or establish that V2 works end-to-end.
