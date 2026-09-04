# Historical validation gate

Real defects, from the real history of real projects, given to the Verified
Work Plane blind: the author of the Work Contract does not know the defect, and
the verdict is frozen before the defect is disclosed.

    cases            3 conclusive
    false CONVERGED  0
    protocol         intact; H02 and H03 sealed mechanically
    raw case files   docs/qualification/h0{2,3}-case.json

| case | project | category | classification |
|---|---|---|---|
| H01 | HireLens | integration / orchestration invariant | **DETECTED** |
| H02 | Seno Dynama | exposed state surface / audio-thread contention | **DETECTED** |
| H03 | Seno Materia | cross-platform GPU, FFI safety, resource release | **INDIRECTLY_EXPOSED** |

## H01 — DETECTED

The project's own unit tests were green and its documented validation boundary
was correct in isolation. The blind contract separated two sentences the
project's own documents treated as one — "present in the source CV" versus
"present in the mutable field later in the pipeline" — and drove the real
compiled binary against a hostile model over HTTP. Scenario C accepted a skill
the model had introduced upstream through its own extraction, wrote the adapted
CV, and rendered the skill. That is exactly the orchestration the historical fix
repaired. Full packet: `docs/REVIEW-PACKET-H01.md`.

## H02 — DETECTED

Ticket promised the host interface a set of live values, including per-block
input and output waveform peaks. The contract asked only whether each promised
value had an exported accessor. Two did not.

    crate-tests              PASS  101 tests, 0 failed
    ui-accessor-surface      FAIL  input waveform peak, output waveform peak
    ui-read-path-nonblocking FAIL  6 read accessors take the audio callback's mutex

The sealed defect was precisely the missing pair: no ring buffer, no accessor,
nothing for the host display to read. The historical fix added lock-free ring
buffers and two exported symbols.

The second finding was not the sealed defect and is not a false positive: the
historical fix explicitly built the new accessors lock-free "without taking any
lock that the audio thread might hold", while the six existing accessors still
take it. The gate found a live instance of the property the fix was honouring.

## H03 — INDIRECTLY_EXPOSED

Strict classification, and worth being strict about.

    crate-tests                  PASS  46 tests
    ffi-null-safety              FAIL  plugin_activate dereferences a host pointer unguarded
    gpu-capability-negotiation   FAIL  device limits requested without consulting the adapter
    multi-instance-safety        FAIL  a process-wide static input queue is shared by every instance

The sealed defect was `caps.formats[0]` panicking across the FFI boundary on an
adapter reporting no formats, plus a leak of the `clap_plugin` box in
`plugin_destroy`. **The contract named neither.**

What it did do: the GPU finding lands at `renderer.rs:64`, and the sealed panic
is at `renderer.rs:77` — same function, same class of fault, an unchecked
assumption about what the adapter provides. A reviewer following the finding
reads the defect on the way. That is exposure, not detection, and it is
classified as such.

The honest failure is mine, not the engine's. The ticket's REQ-2 said the
plugin "shall not leak memory during normal operation, parameter changes, or
when closed" — and I wrote no verification for it at all. The leak was
representable and I did not represent it. Per the gate's own analysis order:

    defect representable?      yes
    contract insufficient?     yes -- REQ-2 and REQ-3 carried no specification
    traceability insufficient? no
    engine wrong?              no -- NOT_CONVERGED was correct, no false CONVERGED

## What three cases establish, and what they do not

Establishes: on three real defects the plane never returned a false CONVERGED.
Twice it named the defect from requirements alone, with the projects' own test
suites green — 101 and 46 passing tests respectively, and 28 in H01.

Does not establish: that a blind contract will always cover every requirement.
H03 shows the opposite, and shows where the ceiling actually is. The plane
verifies what the contract declares. It does not invent the declaration, and a
requirement nobody wrote a specification for is not checked by anything.

## Blindness

- H01: sealed by the organiser by hand; blindness rests on conduct plus commit
  ordering. A fix-commit SHA prefix appeared in an incoming message, was
  declared inert, and was never used.
- H02, H03: sealed mechanically with `scripts/workplane_historical_case.py`.
  The seal→record→reveal transition proves the verdict existed before
  disclosure. Selection was performed by a separate harness (OpenCode) in a
  separate context; the evaluator received only the snapshot and a sanitized
  ticket.
- H03 leak, declared: the two commit SHAs appeared in a command echo. They were
  never looked up.
- One repository was discarded before use: its commit log was printed during
  staging and named fix commits, so it was marked BLINDNESS_COMPROMISED and not
  used. The operator staging a case must not enumerate history — that is a
  protocol lesson this gate paid for.
