# Review Packet — Authority Hardening, Round 2

For the reviewer who found four P0s in `13d2550`. Everything below is what
changed, what proves it, and what is still open.

## Revision

```text
audited by the reviewer   13d25509ce733ed6f851c88cbbfabc18a93d9280
this packet describes     4c8d1c3
branch                    spec
pull request              #16
```

## Findings, reproduced before anything was changed

Every one was demonstrated against `13d2550` first, because a fix for a finding
that does not reproduce is a fix for nothing.

| Finding | How it reproduced |
| --- | --- |
| P0-1 forgeable evidence | A complete `verification_run` written by hand — every digest read from committed state and the checkout, no command executed — returned `CONVERGED`. A second run showed it masking a verification that genuinely failed. |
| P0-2 conflated provenance | The work directory sat outside the repository and still inherited `GIT_RECORDED` from the checkout it merely described. |
| P0-3 ranked provenance | `TRUST_LEVELS["SIGNED"] >= TRUST_LEVELS["CI_APPROVED"]` was `True`. |
| P0-4 self-weakening | A failing check became `CONVERGED` after rewriting the command it is judged by, committed through the controller. |
| P1-1 to P1-4 | Read directly in `trust.py`, `evaluator.py` and `runner.py`; each is asserted by a new case rather than argued. |

## Commits

```text
1bbdeb4  fix(workplane): authenticate evidence by producing it
e143514  fix(workplane): separate provenance domains and drop the ranked ladder
802eda0  hardening: authorize every change to the success conditions
5bd65f6  fix(workplane): bind root transitions to content and give the registry a schema
4c8d1c3  docs: record the second-round findings, decisions and residual limits
```

## Changed files

```text
ainative_workplane/  provenance.py (rewritten), evaluator.py, controller.py,
                     trust.py, authorization.py, contracts.py, runner.py,
                     convergence.py, cli.py, __init__.py
tests/               test_workplane_authority_origin.py (new), and the
                     authority, adversarial, controller, authorization,
                     runner, cli, contracts and substance suites
docs/                ADR-0003, THREAT_MODEL, ARCHITECTURE, FRESHNESS_POLICY,
                     VERIFIED-WORK-PLANE-V2-DOD
scripts/             workplane_qualification.py, workplane_pilot.py
.github/workflows/   ci.yml
```

## A72-A90

All green. Case-by-case placement, since several moved from where the reviewer
expected them and a reviewer should not have to hunt:

| Case | Where | Note |
| --- | --- | --- |
| A72, A73 | `test_workplane_authority_origin.py` | Forged run ignored; no evidence-directory parameter |
| A74-A76 | `test_workplane_authority.py`, `provenance.py` | Authority observed at its own location; the fixture's work directory now lives in the repository it governs, which is what gives it a provenance at all |
| A77-A79 | `test_workplane_adversarial.py` | No fact substitutes for another |
| A80-A83 | `test_workplane_authority.py::SuccessConditionMutationTests` | The four ways to lower the bar, each refused at write time |
| A84, A85 | `test_workplane_authorization.py` | Claimed approval provenance is not read |
| A86 | `test_workplane_runner_convergence.py` | Successor content changed after approval |
| A87, A88 | `test_workplane_authority.py` | Wrong revision, wrong work UID |
| A89, A90 | `test_workplane_authority_origin.py` | One registry validator for both paths |

## CI

```text
33736855246  4c8d1c3  success
33736469546  5bd65f6  success
33735761227  e143514  success
33734735027  1bbdeb4  success
```

Each runs the V2 matrix on `ubuntu-latest` and `windows-latest`, the package
install with its console entry point, and the deterministic scripts. Local:
132 tests, 2 platform skips that execute on the Linux leg.

## What the reviewer should look at first

Three places where a decision was taken that a reviewer may reasonably reject:

1. **Evidence is produced, not authenticated** (ADR-0003 §1). Convergence now
   costs a full verification run and evidence is not reusable. If reusable
   attested evidence matters more than that, the design is wrong.
2. **The mutation bar covers every normative artifact** (§4), including
   requirements and tasks, not only the trust base. This makes ordinary
   authoring require approvals.
3. **Per-evidence freshness is now a race check** (§1). Staleness is prevented
   by not reusing evidence rather than by detecting it. A57 was restaged
   accordingly; if that is a loss rather than a consequence, say so.

Also worth checking: A54-A70 were restaged. They planted files in `runs/`, and
files are no longer read. The questions are asked through two declared
verifications and through the binding comparison instead. A reviewer should
confirm nothing was quietly weakened in that move.

## Still open

```text
HISTORICAL   no blind case has been run; the protocol enforces blindness by
             construction but needs a defect hidden from whoever authors the
             contract, and one agent cannot hold both roles

PILOT        both pilot scripts declare external_harness: false; the section 48
             protocol across two real AI harnesses has not been executed
```

## Known limitations, not defects

- `git_reviewed` and `ci_verified` cannot be observed from a checkout, so a
  policy requiring either cannot be satisfied by this build.
- A mutation approval and a transition approval are records, not signatures. In
  a single-maintainer repository this stops an agent from silently rewriting
  its own bar; it does not stop the maintainer who writes both sides.
- The snapshot race check compares size, mtime and inode; a rewrite preserving
  all three is undetected.
- Assigning a spawned command to its OS container has a microsecond window;
  a process created inside it is caught by the PID-tree fallback.

## Verdict

```text
P0 = not claimable
P1 = not claimable
PRODUCTION = NO-GO
MERGE spec -> main = NO-GO
```

Not claimable rather than zero, on purpose. The previous round closed five
findings, each held by an end-to-end case, green on two platforms — and this
review found four more P0s in what those cases did not ask.
