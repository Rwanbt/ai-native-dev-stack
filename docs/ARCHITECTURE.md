# Verified Work Plane V2 — Architecture Baseline

## Purpose

The Verified Work Plane (V2) lets an agent or developer represent declared work, run
approved verification independently, and decide deterministic convergence for one
repository state.

This document records the PR-00 boundary and, in "Implemented runtime" below, what
the branch actually contains today. Where the two disagree, the runtime and its tests
are the authority; PR-00 prose is historical.

## Implemented runtime

| Module | Responsibility |
| --- | --- |
| `contracts.py` | Twelve versioned schemas, prefixed ULIDs, canonical JSON and digests, portable paths |
| `controller.py` | Sole normative writer: immutable revisions, manifest-last commit, crash and stale-lock recovery |
| `snapshot.py` | Scoped, security-checked repository snapshots bound to a checkout head |
| `runner.py` | Argv-only execution with timeout, bounded streaming output, redaction, append-only runs |
| `isolation.py` | OS container per command so nothing it spawns outlives the run |
| `substance.py` | Adapters that decide whether output contains what was required |
| `evidence.py` | The single validated `verification_run` convergence accepts |
| `trust.py` | Fail-closed policy commitment, approval-root chain and provenance evaluation |
| `freshness.py` | Contract, scope, dependency, registry, policy, root, specification and repository drift |
| `traceability.py` | Structural graph, deterministic gaps, relationship scope coverage |
| `authorization.py` | Waivers and human approvals, effective only under the policy that configured them |
| `convergence.py` | `CONVERGED`, `NOT_CONVERGED`, `INVALID`, `INTERNAL_ERROR` and their exit codes |
| `provenance.py` | Independent provenance facts, observed per object and per domain |
| `authorization.py` | Waivers, human approvals and the mutation bar |
| `evaluator.py` | The authoritative boundary: committed state in, verdict out |
| `cli.py` | Thin headless facade: `work`, `verify`, `converge`, and a labelled `debug` |

## Kernel and boundary

There are two convergence surfaces and confusing them is the whole risk:

- `converge()` is a **pure kernel**. It decides from the traceability,
  evidence, trust and freshness objects it is handed. That is what makes it
  unit-testable, and exactly what makes it unsafe to expose: whoever supplies
  its inputs decides its verdict.
- `evaluate_work(work_dir, repository_root)` is the **authoritative
  boundary**. It accepts two paths and derives everything else — contract,
  policy, approval root, registry, specifications, observed provenance,
  per-evidence trust, per-evidence freshness — from committed state and from
  the checkout. Its signature takes no contract, policy, root, registry, trust
  verdict or freshness result, and a test asserts that it never will.

Production code and the CLI use the boundary. Tests may use the kernel.

Two properties of the boundary are worth stating because they cost something:

- **It produces the evidence it judges.** A recorded run is a file, and a file
  is whatever its author wrote; against a local actor no signature settles
  that. So `evaluate_work` executes the declared verifications rather than
  reading them, and a verdict costs a full run. See ADR-0003.
- **It refuses a change to the rules that the previous authority did not
  approve.** The controller is the only writer, and now also checks that a
  change to any normative artifact carries a `mutation_approval` issued under
  the policy in force *before* the change.

Known limitations, stated rather than implied: no blind historical validation has
been run ([protocol](verified-work-plane-v2-historical-validation-protocol.md)), and
no pilot has been driven by two actual AI harnesses. See
[the definition of done](VERIFIED-WORK-PLANE-V2-DOD.md).

## What exists today

| Existing owner | Responsibility | V2 relationship |
| --- | --- | --- |
| `install.py` | Per-project installation of AI-doc tooling, skills, rules, and an optional pinned gstack checkout | Reuse only as a distribution precedent; do not add the V2 runtime here before a distribution ADR. |
| `scripts/install_agents.py` and `scripts/vault_protocol.py` | Global harness setup, vault discovery, slug validation, path confinement, maintenance-lock and validator checks | Reuse the trust-boundary patterns; V2 must not duplicate or reinterpret vault authority. |
| `scripts/vault_sync.py` | Validates a v4 vault before staging and pushing sync changes | Remains vault synchronization, not Work Contract storage. |
| `hooks/session-start-memory` and `hooks/session-end-save` | Read/write optional session memory via local Obsidian REST endpoints | Remain optional providers; no convergence verdict may depend on them. |
| `.github/workflows/ci.yml` | Cross-platform Python, hook, installer, and static convention gates | Future V2 commands must be headless and add explicit CI gates rather than altering existing gate meaning. |
| `stack/agents/anti-debt/` | Independent deterministic debt analysis | May contribute read-only findings later; it must not decide whether a Work Contract converges. |

## Target boundary

```text
trusted project policy + registered commands
                 │
                 ▼
           Work Controller
                 │
       immutable Work Contract revisions
                 │
                 ├───────────────┐
                 ▼               ▼
       Verification Runner   Repository Snapshot
                 │               │
                 └───────┬───────┘
                         ▼
               Deterministic Convergence
                         │
                    verdict + gaps

optional, read-only inputs: vault memory | Graphify | ADRs | anti-debt
```

The Work Contract is the sole operational authority. Narrative plans and vault memory
provide provenance and context but never become executable policy by prose alone.

## Ownership rules

- The Work Controller is the only supported normative writer.
- The command registry and project policy are part of the trust base. A controlled
  implementation cannot silently change either and then claim its own success.
- The runner receives a registered `argv` array, never an arbitrary shell string.
- Verification runs and convergence records are append-only evidence, bound to a
  captured repository state.
- A language model may suggest gaps or prose, but never emits a blocking PASS/FAIL
  verdict without deterministic evidence.

## PR-00 decisions deferred

- **Distribution decision:** V2 will be a first-party Python package named
  `ainative_workplane`, with `python -m ainative_workplane` as the canonical developer
  invocation. Shell and PowerShell entry points may be thin wrappers only. The package
  owns its runtime and schema compatibility version; the root `VERSION` remains the
  version of the existing AI-Native Dev Stack. PR-01 must define package metadata and
  schema-discovery compatibility, but must not change this ownership decision.
- The on-disk V2 format, schema tooling, UID implementation, and controller are PR-01
  and PR-02 work, after review.
- Graphify, Obsidian, Spec Kit, and anti-debt integrations remain providers rather than
  core dependencies.

## Trust baseline and mutation protocol

### The project trust anchor comes first

A project is bootstrapped before any work contract exists:

```text
UNINITIALIZED  --explicit bootstrap-->  GOVERNED  --> work creation
```

`ainative trust bootstrap` writes `.ai-native/trust/project_trust.json`, which pins the
approval root the project starts from, the key fingerprints it authorizes to approve, and
the predicate the anchor itself must satisfy. Creating a work directory is a local act and
never establishes what a project trusts: a work no anchor pins is
`PROJECT_TRUST_UNINITIALIZED`, which is `INVALID`, and a work naming a root the anchor does
not pin is refused as `UNGOVERNED_GENESIS`. See ADR-0004.

The anchor is written **exactly once**: it must have a single commit in its history, and
that commit must satisfy its predicate against the identities the anchor itself pins.
Without the first condition the second is circular — an actor that rewrites the anchor to
add its own key would be measured against the list it just wrote. Changing a governed
project's authorized signers is therefore not an edit but a new anchor, which is what a
root of trust should cost. See ADR-0005.

> **The bootstrap ceremony is inside the trusted computing base.** A root of trust cannot
> prove its own legitimacy from data whose authority comes from that root. Before a trusted
> anchor exists, an actor able to run commands and commit can generate a key, configure Git
> to verify it, name its own fingerprint as authorized, and sign the anchor — and every
> later check then passes truthfully. The Work Plane's guarantees begin *after* a trusted
> operator has established the anchor; it cannot distinguish that operator from an agent.
> `initialized_by` is metadata the caller supplied and nothing verifies it.
>
> **Deployment requirement: trusted bootstrap must precede controlled-agent access.**
> `ainative trust bootstrap` is a privileged operation and labels its output
> `"authority": "privileged_trust_establishment"`. See ADR-0006 and case A101.

The anchor pins the *genesis* approval root, not the current one, and deliberately does not
pin the policy. Policy evolves through authorized mutation: each root carries the policy
commitment it was established under, the manifest records the committed policy chain
alongside the root chain, and **a transition is judged under its predecessor's policy** —
its predicate and its required facts — so a later, weaker policy cannot retroactively
authorize a transition it never saw.

A root must carry the commitment of the policy it is written with, and the controller
refuses a revision where they disagree. Atomicity follows: a new policy commitment changes
the root's own commitment, and a changed root already requires a predecessor and a
transition approval, so policy and root move together in one approved mutation.

**A transition is judged by the evidence bound to it, not by today's authority.** When the
controller authorizes a rotation it records, in the manifest's `root_chain` entry, the
commit that carried the approval and that approval's digest. The evaluator re-establishes
each transition's facts from that commit — immutable, so the same question gets the same
answer every time — and a transition with no bound evidence is invalid. See ADR-0007.

An approval names both ends of the change it authorizes: `mutation_approval` binds
`base_digest` as well as `target_digest`, so it authorizes one transition rather than one
destination and cannot be replayed to undo a later strengthening. `work_creation_approval`
is content-addressed instead — genesis has no base, and two works with byte-identical
contracts sit at the same bar.

### Authority is decided before anything executes

`evaluate_work` establishes the whole of the authority — the verified project anchor, the
work's admission, the current policy and root, the complete root chain with each
transition's own evidence — **before a single registered command starts**. If any of it
cannot be established the verdict is `INVALID` and **zero verification commands run**.

A verdict that fails closed after the fact is not the same as never having let an authority
nobody could validate decide what executes. `evaluate_authority_trust()` is the pure
function that answers everything decidable without an evidence run; `evaluate_trust()` then
adds only the evidence-specific checks — binding, required evidence facts, freshness,
substance, result. See ADR-0008.

Two consequences worth stating. A contract satisfied entirely by human approval produces no
evidence, and therefore used to skip the chain walk altogether; it no longer can. And a
broken chain is now a standalone `ROOT_OF_TRUST_INVALID` gap — `INVALID`, exit code 2 —
rather than a reason buried in one run's ineligibility, because a chain nobody can evaluate
is not the same as work that is unfinished.

**Authority precedence.** Authority is decided first, so an authority that cannot be
established is reported instead of, not alongside, an evidence-level reason. A policy that
demands a fact of its own authority that nothing can establish makes the work unevaluable,
not merely unverifiable.

### Creating a work contract proposes; admission promotes it

Revision 1 states the whole of what a work must accomplish, so it is a success condition
exactly as later revisions are. A work is admitted by a `work_creation_approval` at
`<work>/creation_approval.json`, binding the anchor, the exact initial normative digest and
the anchor's predicate. The controller refuses to write an unadmitted work; the evaluator
refuses to converge on one, recomputing the genesis digest from `revisions/1/` rather than
reading a field. Absent or unsatisfied, the verdict carries `WORK_NOT_ADMITTED`.

### A predicate is a mechanism

`predicate_id` names a mechanism with a fixed fact requirement, not a label the policy is
free to interpret:

| predicate | requires | an actor with commit rights can satisfy it |
| --- | --- | --- |
| `signature` | `signature_verified` | no |
| `git_review` | `git_reviewed` | no |
| `ci_attestation` | `ci_verified` | no |
| `recorded_owner_ack` | `git_recorded` | **yes**, and it is named to say so |

`required_mutation_facts` may add to a predicate's requirement and never subtract from it.
A predicate this build does not implement is never satisfied.

**The supported production default is `signature`.** It is the one predicate with a real
provider here, and it asks two separate questions:

- *cryptographic validity*, which Git decides: `%G?` must be `G` against the configured
  keyring or allowed-signers file;
- *authorization*, which Git cannot decide: the signing key fingerprint (`%GF`) must appear
  in the anchor's `authorized_signers`. A repository may accept several signing identities,
  and being allowed to sign ordinary commits is not being allowed to approve a policy
  change. Where no set is pinned, nothing is established — not "any valid signature".

Provenance over a *set* of objects is conjunctive: the signing identity is resolved per
path, and one signed commit never stands in for a path whose content came from an unsigned
one.

`git_reviewed` and `ci_verified` are modelled as independent facts because they are real
and independent, but nothing in this build can establish either, so a policy requiring one
fails closed. That is a functional limit, stated rather than approximated -- and it is why
`git_reviewed` is no longer described as the portable default.

A local commit is `git_recorded`, never automatically reviewed. If an observed path is
dirty or untracked, nothing is established about it at all.

The initial manifest is created only by the Work Controller. Later loads canonicalise
each referenced artifact and compare its digest with the manifest: mismatch becomes
`UNEXPECTED_MUTATION`; an unreadable pointer or invalid manifest becomes `INVALID`.
Controller staging lives beneath `<work>/.staging/<transaction-id>/`, never system temp.
It writes staged artifacts, promotes them to immutable revisions, then atomically replaces
the manifest last. Directory/file sync is best effort where the platform supports it; it
is not a claim of power-loss durability.

Verification substance is runner-specific: PR-04 owns adapters for known tools and a
documented fallback for custom commands. Exit status alone never proves substance.

## Test path planned for later phases

```text
create contract → mutate through controller → implement repository change
→ capture snapshot → run registered command → inspect substance
→ converge or report deterministic gaps
```

Each arrow needs an integration test. Mutation, snapshot, path safety, registry
tampering, stale scope, crash point, and prompt-injection cases need negative tests.
