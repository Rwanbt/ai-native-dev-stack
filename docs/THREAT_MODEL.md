# Verified Work Plane V2 — Threat Model

## Security statement

V2 can establish deterministic local evidence. It is not a sandbox, a code-signing
system, or protection against an actor controlling the host, checkout, and Git history.
`local_untrusted` must never be described as isolation.

## Assets and trust boundaries

| Asset | Required protection | Boundary |
| --- | --- | --- |
| Work Contract revisions and manifest | Immutable artifacts, digest verification, manifest committed last | Work Controller |
| Command registry and policy | Provenance check and change detection | Trusted project configuration |
| Repository snapshot | Canonical paths and content digest | Runner before execution |
| Verification output | Size limits and secret redaction | Runner output capture |
| Verdict and gaps | Deterministic derivation from committed state and runs | Convergence engine |

## Threats and required mitigations

| Threat | Failure prevented | Required V2 control |
| --- | --- | --- |
| A task edits its own acceptance conditions | False convergence | Controller-only mutation, expected revision, immutable revisions |
| Registry is changed to weaken tests | Verification is misrepresented as approved | Registry digest and provenance in the snapshot and run |
| Policy or waiver is changed to weaken a verdict | Unreviewed exception becomes authority | Approved policy baseline, policy-change invalidation, explicit waiver provenance |
| Direct manifest edit or malformed genesis | Contract state is silently replaced | Controller-only genesis, digest validation, `UNEXPECTED_MUTATION` / `INVALID` |
| Shell text is injected through a plan | Unreviewed execution | Registered `argv` only; narrative files are non-normative |
| Repository changes after a green run | Stale success claim | Scope and dependency freshness checks |
| Path traversal, symlink escape, case collision, device/FIFO | Snapshot ambiguity or host data access | Canonical repo-relative path policy and explicit security rejection |
| A command exits zero without testing substance | False positive verification | Command-specific substance adapters and suspicious-result status |
| Logs disclose credentials | Secret exposure | Redaction, output truncation, no raw unbounded output |
| Crash during a mutation | Previous valid contract lost | Stage, promote immutable artifacts, atomically replace manifest last |
| Long-running command or prompt text in `spec.md` | Denial of service or injected execution | Timeout, output limits, and non-normative prose with registered `argv` only |

## Non-goals

V2 does not protect against root compromise, compromised kernels, malicious CI
administrators, rewritten remote history, or a user with unrestricted write access.
Git-recorded evidence is not automatically Git-reviewed evidence.

## Existing repository controls reused as evidence, not dependencies

`scripts/vault_protocol.py` already demonstrates slug validation, path confinement,
symlink escape rejection, maintenance-lock checks, and validator failure reporting.
The V2 core may reuse these design properties but must own its own contract format and
must work when the vault is absent.
