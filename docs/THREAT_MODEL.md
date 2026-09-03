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

## Authority threats and what closes them

Each row names what an attacker who controls the agent — but not the reviewer,
the checkout's history, or the host — can attempt, and the case that proves it
is refused.

| Threat | Attacker capability | Impact if unmitigated | Mitigation | Residual risk | Test |
| --- | --- | --- | --- | --- | --- |
| Arbitrary contract injection | Write any JSON file on disk | Convergence against an easier contract than the committed one | The evaluator takes a work directory; no contract argument exists | An attacker who can write through the controller changes committed state, which is visible in the manifest | A54, A68 |
| Arbitrary policy injection | Supply a policy that lowers its own bar | Trust satisfied by a weaker rule than the governed one | Policy is read from committed state and its commitment is bound into evidence | Same as above | A61, A70 |
| Arbitrary root injection | Supply an approval root it controls | Self-granted authority | Root is read from committed state; evidence must bind that exact root reference | Same as above | A69 |
| Forged declared provenance | Write `"SIGNED"` or `"GIT_REVIEWED"` into evidence or a root | Claimed authority accepted as established | Declared provenance is capped at what the checkout can be observed to support | GIT_REVIEWED and CI_APPROVED are not observable at all here, so policies requiring them cannot be satisfied | A55, A56 |
| Forged freshness input | Supply a current-identity fixture naming old digests | Stale evidence presented as fresh | Freshness is recomputed from the checkout per specification; no fixture is accepted | A file rewritten with identical size, mtime and inode during hashing is undetected | A57, A66 |
| First-evidence trust inheritance | Order a trusted run before an untrusted one | Weak evidence laundered by a strong neighbour | Every run carries its own assessment; only individually eligible runs count | — | A59 |
| First-evidence freshness inheritance | Order a fresh run before a stale one | Stale evidence counted | As above | — | A58 |
| Root predecessor link without authorization | Write a successor root naming the trusted one as parent | Inherited authority without consent | A successor must carry a transition_approval naming that exact successor under the policy's predicate | The approval is a record, not a signature; a maintainer who can write both roots can write both | A62 |
| Partial mutation deleting success conditions | Mutate one artifact | Requirements and criteria silently removed | A revision is the previous set with explicit replacements and explicit deletions | — | A63 |
| Schema-less normative artifact | Commit `{"tasks": {...}}` with no schema | Unvalidated data read as authority | Normative names must validate; other names are marked non-normative and never read | — | A64 |
| Unknown gap waived | Wait for a gap code nobody classified | Future gaps waivable by default | Waiver eligibility is an allowlist of eight completeness gaps | — | A67 |
| Snapshot read during a write | Rewrite a scoped file while it is hashed | A digest of a state that never existed | Size, mtime and inode are compared before and after hashing | A rewrite preserving all three is undetected | A71 |

## Authority threats found by the second review

The first table above covers attacks that supply authority as an argument.
These are the harder ones: manufacturing the things the evaluator does accept.

| Threat | Attacker capability | Impact if unmitigated | Mitigation | Residual risk | Test |
| --- | --- | --- | --- | --- | --- |
| Forged verification evidence | Write a file in the work directory | A hand-written PASS converges, and masks a verification that actually fails | The evaluator executes the declared verifications and judges only what it produced; recorded runs are an audit trail | Convergence costs a full run, and reusable evidence needs an attestation this build cannot verify | A72, A73 |
| Provenance domains conflated | Put the work directory anywhere | A directory outside the repository inherits the checkout's cleanliness | Two observations: the checkout for the code, the normative artifacts at their own location | The run log is excluded from the authority observation by name, not by a general rule | A74-A76 |
| Ranked provenance | Sign a commit | A signature satisfies a policy that demanded CI or review | Independent facts; no fact substitutes for another | `git_reviewed` and `ci_verified` are unobservable here, so policies requiring them cannot be satisfied at all | A77-A79 |
| Success-condition self-weakening | Commit through the controller | Rewrite the command, specification or policy you are judged by, then pass | Every normative change needs an approval the policy of revision N gives for exactly revision N+1 | The approval is a record, not a signature; a sole maintainer can write both sides | A80-A83 |
| Forged approval provenance | Write `"SIGNED"` in a waiver | An exception removes a gap on its own say-so | The claim is not read; the artifact's observed facts are | As above | A84, A85 |
| Successor content swapped after approval | Keep the UID, change the contents | Approved lineage carries unapproved rules | The approval binds `successor_commitment`, a digest of the candidate's content | — | A86 |
| Evidence bound to another work or revision | Reuse a correct digest | A run from elsewhere counts here | Binding checks work UID and contract revision, both derived from the manifest | — | A87, A88 |
| Registry accepted by one path, refused by the other | Commit a registry the runner would reject | Divergent trust base | One validator, called by both the contract and the runner | — | A89, A90 |

## Authority threats found by the fifth review

| Threat | Attacker capability | Impact if unmitigated | Mitigation | Residual risk | Test |
| --- | --- | --- | --- | --- | --- |
| Self-authored initial contract | Create a directory in a governed project | Choose a trivial requirement, criterion and verification for a sibling work under the project's legitimate root, and converge on a bar nobody agreed to | A `work_creation_approval` binds the anchor and the exact genesis normative digest; the controller refuses to write an unadmitted work and the evaluator refuses to converge on one | Under `recorded_owner_ack` the actor can record its own admission | A97 |
| Valid signature by an unauthorized signer | Hold any key the repository's verifier configuration accepts | Satisfy the production-default predicate without being anyone the project authorized to approve | The anchor pins `authorized_signers` by key fingerprint, and the signer must appear there | A project that loses its key cannot rotate signers without a new anchor | A98 |
| Widening the verifier configuration | Add a key to `gpg.ssh.allowedSignersFile` or `.git/config` | Make Git verify your own signature and inherit authority from it | Git decides what verifies; the anchor decides what is accepted, and the anchor must have exactly one commit in its history | The anchor file can be overwritten — it then establishes nothing, which fails closed | A98 |
| One signed commit signing a whole set | Commit one signed change touching any observed path | A path whose content came from an unsigned commit is reported as signed | The signing identity is resolved per path; a set is verified only when every member is | One `git log` per observed path | A99 |
| Predecessor-less root as second genesis | Change the approval root's content | Replace the root without a transition approval, making the chain invariant optional exactly where it decides something | The controller requires a predecessor naming the committed root plus a transition approval; the chain terminates only at the anchor's pinned genesis | None known for this path | A100 |

## Authority threats found by the fourth review

| Threat | Attacker capability | Impact if unmitigated | Mitigation | Residual risk | Test |
| --- | --- | --- | --- | --- | --- |
| Self-recorded approval read as review | Write and commit in the repository | Build the exact `mutation_approval` your own weakened state needs, commit it, and satisfy a policy whose predicate is *named* review while requiring only `git_recorded` | A predicate is a closed mechanism with a fixed fact requirement (`predicates.py`); the policy's own requirement may only add to it | Under `recorded_owner_ack` an actor with commit rights is still the whole bar -- named, not removed | A94 |
| Agent-chosen genesis | Create a directory | Establish your own policy, approval root, registry and rules, and operate under the trust anchor you picked; every N to N+1 protection becomes irrelevant | Project trust is bootstrapped before work creation and pins the genesis root; an unpinned work is `PROJECT_TRUST_UNINITIALIZED` and therefore `INVALID` | Under a `recorded_owner_ack` anchor the actor can still write and commit the anchor itself | A95 |
| Orphan revision read as history | Interrupt a commit between promotion and manifest replace | A root from a revision that was never committed enters the trust chain as historical authority | The committed root chain lives in the manifest, which is the commit marker; each historical root is re-digested when read | None for this path: the chain is written inside the marker, so a revision enters history exactly when it becomes committed | A96 |

## Authority threats found by the third review

| Threat | Attacker capability | Impact if unmitigated | Mitigation | Residual risk | Test |
| --- | --- | --- | --- | --- | --- |
| Self-issued mutation approval | Call the controller API | Build the exact record that authorizes your own weakened next state, and converge behind it | The approval is a path; the controller observes that artifact's own provenance | Under `git_recorded` an actor with commit rights can still record one — visibly, in history. Only `signature_verified` excludes an actor without the key | A91, A92 |
| Authority rewritten during evaluation | A registered command has a filesystem | Rewrite the manifest, policy or registry mid-run and be judged on the state loaded before | Authority is re-read and compared after the runs; any drift is `AUTHORITY_CHANGED_DURING_EVALUATION`, which is unevaluable | The comparison is at the end, not continuous; a change made and reverted within one run is undetected | A93 |

## Trusted computing base

Everything a verdict depends on, and nothing else:

| In the TCB | Why |
| --- | --- |
| `ainative_workplane/` runtime modules | They compute the verdict |
| The Python interpreter and its standard library | The runtime has no third-party dependency |
| The project policy and approval root in force | They decide what authority means |
| The command registry | It decides what may execute |
| The Git checkout the snapshot reads | It decides what was verified |
| The operating system's process, filesystem and job primitives | They bound execution |

| Deliberately outside | Consequence |
| --- | --- |
| The vault, Graphify, anti-debt, ADRs, memory, `spec.md` prose | May inform, never decide; a verdict must be reproducible with all of them absent |
| Any language model | May propose requirements, gaps or waivers; a proposal carries no authority until a controller writes it and a policy authorizes it |
| The CLI | Thin: it loads JSON and prints what the engine returned |

## Controls implemented on this branch

Every row of the threat table above is exercised by `tests/test_workplane_adversarial.py`,
which maps cases A01-A53. Two rows carry a known residual risk, stated rather than
implied:

- PID reuse: the stale-lock recovery treats an unreadable or foreign lock as held, and
  a recycled PID reads as alive, so it errs toward refusing to reclaim.
- Secret redaction is pattern-based defense in depth. Persisted evidence keeps digests
  and a bounded preview rather than full logs precisely because redaction can miss.

## Non-goals

V2 does not protect against root compromise, compromised kernels, malicious CI
administrators, rewritten remote history, or a user with unrestricted write access.
Git-recorded evidence is not automatically Git-reviewed evidence.

## Existing repository controls reused as evidence, not dependencies

`scripts/vault_protocol.py` already demonstrates slug validation, path confinement,
symlink escape rejection, maintenance-lock checks, and validator failure reporting.
The V2 core may reuse these design properties but must own its own contract format and
must work when the vault is absent.
