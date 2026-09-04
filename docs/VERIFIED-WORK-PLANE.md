# The Verified Work Plane

A deterministic gate between an agent claiming work is done and the project
believing it. It decides one question — *has this work converged?* — from
committed contracts and executed verifications, and from nothing else. No
narrative reaches the verdict. Neither does anything the caller passes in.

This page is the current state of the system. The `REVIEW-PACKET-*` files are
audit history; you do not need to read them to use or review this.

## What it is not

- Not a test runner. It runs verifications, but the answer it produces is about
  a contract, not about a process exit code.
- Not a CI system. It has no scheduler, no queue, no workers.
- Not a sandbox. It does not contain a hostile agent; it refuses to *believe*
  one. An agent that can write to the repository can still write to it.
- Not a substitute for review. It proves declared properties were checked, not
  that the right properties were declared.

## The shape of it

    project trust anchor        pins what the project trusts, once, by commit
      -> work creation approval binds that trust to one exact genesis
        -> work contract        requirements, criteria, tasks, verifications
          -> verification       committed commands, executed here, evidence bound
            -> evaluate_work()  the only production verdict

Every production surface runs the same authority preflight first. There is no
parameter that skips it.

## Install

    pip install .
    ainative --help

Python 3.8+ on Linux, Windows and macOS. No runtime dependencies.

## Use it

Bootstrap the project's trust anchor. This is a privileged ceremony — see
"What it cannot verify" below.

    ainative trust bootstrap --repo . \
      --approval-root root.json --policy policy.json \
      --by "your name" --predicate recorded_owner_ack
    git add -A && git commit -m "project trust anchor"

Approve creating a work, then create it. The approval binds the anchor to the
exact genesis the contract will carry, so a work nobody admitted is unevaluable
however internally consistent it is.

    ainative work admit .ai-native/work/w1 --repo . --by "your name" \
      --artifact requirements='[...]' --artifact acceptance_criteria='[...]' ...
    git add -A && git commit -m "work creation approval"

    ainative work new .ai-native/work/w1 --artifact requirements='[...]' ...
    git add -A && git commit -m "work contract, revision 1"

Then verify and converge:

    ainative verify --work .ai-native/work/w1 --verification verify_... --repo .
    ainative converge --work .ai-native/work/w1 --repo .

`converge` exits 0 CONVERGED, 1 NOT_CONVERGED, 2 INVALID, 3 INTERNAL_ERROR.

`ainative debug run-command` exists for looking at a command in isolation. It
is non-authoritative by construction: everything it evaluates comes from the
caller, and it never produces a verdict.

## What it cannot verify

The first trust anchor authorises itself. The runtime cannot distinguish a
trusted operator from a controlled agent performing the same ceremony, so
genesis sits inside the trusted computing base rather than under it. The
deployment requirement that follows is concrete: **bootstrap trust before any
controlled agent has access to the repository.** An external trust source is
the only mechanical answer and is deliberately not built. See ADR-0006.

Full boundary in `docs/THREAT_MODEL.md`.

## What has been established empirically

**Authority.** Closed by external review after ten adversarial rounds:
P0 = 0, P1 = 0. Frozen. Reopening it needs a concrete reproducer, not another
speculative pass.

**Historical validation.** Real defects, from real project history, given to
the plane blind — the contract author does not know the defect.

| case | project | category | classification |
|---|---|---|---|
| H01 | HireLens | integration / orchestration invariant | **DETECTED** |
| H02 | Seno Dynama | exposed state surface / audio-thread contention | **DETECTED** |
| H03 | Seno Materia | cross-platform GPU, FFI safety, resource release | **INDIRECTLY_EXPOSED** |

Three conclusive cases, zero false CONVERGED. Twice the plane named a defect
from requirements alone while the project's own suite was green. H03 shows the
ceiling honestly: the plane verifies what the contract declares, and a
requirement nobody wrote a specification for is checked by nothing. Full
analysis in `docs/HISTORICAL-VALIDATION-REPORT.md`.

H01 is worth understanding, because it shows what the gate is actually for.
The project's own unit tests were green and its documented validation boundary
was correct in isolation. The blind contract distinguished two sentences the
project's own documents treated as one — "present in the source CV" versus
"present in the mutable field later in the pipeline" — and built an end-to-end
verification that drove the real compiled binary against a hostile model. That
verification failed on exactly the orchestration the historical fix repaired.
See `docs/REVIEW-PACKET-H01.md`.

**Pilot.** Five real, mergeable changes, each governed and measured through
`evaluate_work()`, across two real AI harnesses.

    2 features, 1 bugfix, 1 refactor, 1 hotfix
    harnesses: Claude Code (Opus 5), OpenCode (MiniMax-M3)
    5/5 CONVERGED   0 false CONVERGED   0 false NOT_CONVERGED
    contract revisions 1 each, 0 normative mutations, no corruption
    convergence 2.5-6.2 s per item, verification 0.3-4.0 s

See `docs/PILOT_REPORT.md`.

## Known limitations, post-v1

- `REUSABLE_ATTESTED_EVIDENCE` and `SELECTIVE_RERUN` are designed for and not
  built. Every `evaluate_work()` re-runs every declared verification. Measured
  cost at pilot scale is seconds; this is a scalability ceiling, not a
  correctness gap. See ADR-0003 §1.
- `git_reviewed` and `ci_verified` predicates are declared and unimplementable
  locally; only `signature` and `recorded_owner_ack` are usable today.
- `execution_scope` entries must be files. A directory is currently reported as
  `SECURITY_REJECTED`, which describes the guard rather than the mistake.
