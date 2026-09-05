# Blind historical validation — case H01

> **STATUS: HISTORICAL QUALIFICATION RECORD** — retained for auditability.
> This document records the state of the Verified Work Plane work at the time
> it was written; it is not the current operational status. See
> [docs/VERIFIED-WORK-PLANE.md](VERIFIED-WORK-PLANE.md) for current state.

The first case of the historical gate. Conducted blind: the contract was built
from a ticket and the snapshot alone, frozen, and only then evaluated.

    snapshot        D:\App\.history-h01\HireLens-H01   (sealed by the organiser)
    baseline        153c8e0  H01 historical baseline
    work_uid        work_01M1N11JG78824PDJ5GQCYK0G8, revision 1
    contract digest 64d618025cf75d30b219bae498cbd024035850e0bcaed218f767b46561b5584f

The digest is the same in all three runs. Two were infrastructure retries; the
contract, the specifications and the registry never changed.

## Runs

    RUN-1  9e1062b  NOT_CONVERGED  4 gaps   INFRASTRUCTURE_INCONCLUSIVE
    RUN-2  a7e1a94  NOT_CONVERGED  4 gaps   INFRASTRUCTURE_INCONCLUSIVE
    RUN-3  a5246e6  NOT_CONVERGED  2 gaps   dynamic specifications executed

RUN-1 and RUN-2 both failed on `cargo build --offline: failed to download
home v0.5.12`. That was not a harness bug and not a sandbox artefact: the crate
was genuinely absent from the cargo cache, reproduced outside the harness. A
`cargo fetch` fixed it and nothing else changed.

Both blocked checks refused loudly instead of reporting a green run over
nothing. That is the only thing RUN-1 and RUN-2 prove, and it is worth having.

## RUN-3, the frozen result

    crate-tests              PASS  28 tests, 0 failed, 2 190 ms
    boundary-reachability    PASS  2 render sites, 2 entry points, 145 ms
    structured-llm-contract  PASS  3 response types closed, 145 ms
    hostile-adaptation-e2e   FAIL  4 observations, 3 findings, 5 304 ms

The end-to-end check drives the compiled `hirelens adapt` binary against a
localhost stub playing a hostile model. It exists because the crate has no
`[lib]` target, so no Rust integration test can reach the pipeline from
outside — and the ticket asked for the boundary to hold for the whole real
pipeline, not only when called in isolation from a unit test.

    A  skill absent from the CV, offered in the adaptation      rejected
    B  bullet not verbatim in the CV                            rejected
    C  skill absent from the CV source, introduced upstream
       by the model's own extraction, then used                 ACCEPTED
    D  legitimate adaptation                          control   accepted

A and B fail closed with the messages the ADR promises. D passes, so the
refusals in A and B are discrimination rather than a build that rejects
everything. C is the finding: exit 0, an adapted CV written for the user, and
the absent skill present in the rendered output.

Scenario C exists because the ticket says a skill must be "présente dans le CV
source" while ADR-0001 says it must "exister dans `cv.skills`". Those are not
the same sentence. Only the second is easy to test, and a contract that tested
only the easy one would not have been answering the ticket.

## Classification

    H01 CLASSIFICATION = DETECTED
    BLINDNESS          = VALID, with a declared SHA-prefix leak (never used)
    FALSE_CONVERGED    = NO

Revealed by the organiser after the verdict was frozen at `a5246e6`; the git
history is the ordering proof.

The sealed defect: the anti-hallucination skill whitelist was derived *after*
`enrich_skills()`, so a model could introduce a skill absent from the source CV
upstream and have `validate_adaptation()` accept it downstream. The historical
fix captured `allowed_skills` from the source CV before enrichment and validated
against that immutable reference.

Scenario C observed exactly that orchestration, and it was reached without any
knowledge of the defect. What produced it was one distinction taken seriously
while writing the contract:

    "present in the source CV"  is not  "present in cv.skills later in the pipeline"

The ticket said the first; ADR-0001 said the second. Testing only the second
would have produced a green run over the live defect.

H01 was sealed by the organiser by hand rather than through
`scripts/workplane_historical_case.py`. Its blindness therefore rests on
conduct plus commit ordering, not on the tool's seal/record/reveal transition.
Later cases should use the tool, so blindness is mechanically checkable instead
of attested.

## What the case cost

    contract revisions       1  (no mutation, no approval beyond admission)
    normative mutations      0
    human interventions      1  (the cargo cache, an environment fault)
    false CONVERGED          0
    false NOT_CONVERGED      0  in RUN-3; RUN-1 and RUN-2 were inconclusive,
                                which the instrument reported as such
