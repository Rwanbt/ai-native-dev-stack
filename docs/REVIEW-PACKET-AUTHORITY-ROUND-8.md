# Review Packet — Authority Hardening, Round 8

One finding. Small round, as asked.

## Revision

```text
reviewed        fa01c41
this packet     b96cb5b
branch          spec
pull request    #16
```

## CI

```text
run 33812309277   every job green
                  Verified Work Plane V2 on ubuntu-latest and windows-latest
```

Local: 153 V2 tests OK (2 platform skips), plus 38 `ai_docs`, 40 `scripts` and
7 `hooks` tests, the three deterministic scripts, and the scope and convention
gates.

## A107 — reproduced against `fa01c41`

```text
the manifest records: ['approval_digest', 'commit']
_transition_facts consumes evidence['commit']:          True
_transition_facts consumes evidence['approval_digest']: False

verdict with a fabricated approval_digest in the chain: CONVERGED
```

The digest was written, required by the schema, and never read back. The
historical binding was to a commit, not to the approval that commit was
supposed to contain — and a commit signature says something was signed, not
what.

## The correction

The chain entry records the path as well:

```json
{"revision": 2, "digest": "...",
 "authority": {"commit": "<sha>", "approval_path": "<repo-relative>", "approval_digest": "<sha256>"}}
```

Reconstruction now: resolve the commit → `git show <commit>:<path>` → parse →
canonicalize → require `canonical_digest == approval_digest` → *only then*
derive provenance facts from that commit. Any step failing leaves the
transition with no entry, and an unbound transition was already invalid.

**The working tree is never consulted for a historical transition.** What is on
disk today proves nothing about what was approved then.

## Exact files changed

```text
ainative_workplane/provenance.py   repository_location(), blob_at_commit()
ainative_workplane/controller.py   _transition_authority() records approval_path
ainative_workplane/evaluator.py    _transition_facts() reads and verifies the object
ainative_workplane/contracts.py    root_chain[].authority.approval_path
tests/test_workplane_authority_origin.py   TransitionApprovalBindingTests
docs/adr/0007-...md, docs/THREAT_MODEL.md, docs/VERIFIED-WORK-PLANE-V2-DOD.md
```

## A107 cases

```text
blocking
  a digest naming another object invalidates the chain
  a path the commit does not hold invalidates the chain
  a commit predating the approval invalidates the chain
     (the file is still in the working tree — that is the point)
control
  the marker records commit, path and digest
  a matching commit, path and digest stay valid
```

Reverting the fix makes the three blocking cases fail; both controls keep
passing.

## One thing I noticed and did not change

A broken root chain surfaces as `ROOT_OF_TRUST_INVALID` **inside the reasons an
individual run was ruled ineligible for**, not as a standalone gap. So the
verdict is `NOT_CONVERGED` where `INVALID` would classify it better — the chain
being unevaluable is not the same as the work being unfinished.

It never produces a false `CONVERGED`, and the review asked for a narrow round,
so it is reported rather than changed. The A107 assertions match what the
system actually reports today, and say so in the test's own docstring. If you
want the classification fixed, it is a one-line change in the evaluator and I
would rather you decide than discover it.

## Status

```text
P0 authority        = not self-certified
P1 authority        = not self-certified
REUSABLE_ATTESTED_EVIDENCE = NOT BUILT
SELECTIVE_RERUN            = NOT BUILT

HISTORICAL = OPEN, no blind case run
PILOT      = OPEN, no two-harness pilot run

PRODUCTION = NO-GO
MERGE spec -> main = NO-GO
```
